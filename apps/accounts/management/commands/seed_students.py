# apps/accounts/management/commands/seed_students.py
import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction, IntegrityError

# Keep common Portuguese connectors in lowercase inside multi-part names.
CONNECTORS = {"da", "de", "do"}


def normalize_name(name: str) -> str:
    name = (name or "").strip().lower()
    parts = re.sub(r"\s+", " ", name).split(" ")
    out = []
    for i, p in enumerate(parts):
        if not p:
            continue
        if i != 0 and p in CONNECTORS:
            out.append(p)
            continue
        out.append("-".join(s.capitalize() if s else s for s in p.split("-")))
    return " ".join(out)


def split_first_last(full_name: str) -> tuple[str, str]:
    full_name = normalize_name(full_name)
    if not full_name:
        return "", ""
    bits = full_name.split(" ", 1)
    if len(bits) == 1:
        return bits[0], ""
    return bits[0], bits[1]


def only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def normalize_cpf(raw: str) -> str:
    d = only_digits(raw)
    if len(d) == 10:
        d = "0" + d
    return d


class Command(BaseCommand):
    help = (
        "Seed student users from CSV with columns: "
        "name,email,cpf[,password][,password_change_required]. "
        "Attaches all to the 'Aluno' group."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to CSV (UTF-8)")
        parser.add_argument("--dry-run", action="store_true",
                            help="Parse and validate without writing to DB")
        parser.add_argument("--reset-passwords", action="store_true",
                            help="Also reset password for users that already exist (by CPF)")
        parser.add_argument("--default-password", type=str, default="hango.teste123",
                            help="Default password to set (new users always; existing only with --reset-passwords)")

    @transaction.atomic
    def handle(self, csv_path, dry_run=False, reset_passwords=False, default_password="hango.teste123", **kwargs):
        User = get_user_model()

        path = Path(csv_path)
        if not path.exists():
            raise CommandError(f"CSV not found: {path}")

        # Ensure the 'Aluno' group exists
        alunos_group, _ = Group.objects.get_or_create(name="Aluno")

        created = 0
        updated = 0
        skipped = 0
        errors = 0

        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            required = {"name", "email", "cpf"}
            fieldnames = {c.strip().lower() for c in (reader.fieldnames or [])}
            if not required.issubset(fieldnames):
                raise CommandError(f"CSV must have columns at least: {sorted(required)}")

            for i, row in enumerate(reader, start=2):  # header is line 1
                raw_name = (row.get("name") or "").strip()
                email = (row.get("email") or "").strip().lower()
                cpf = normalize_cpf(row.get("cpf"))

                pw = (row.get("password") or default_password).strip()
                force_change = str(row.get("password_change_required", "true")).lower() in ("1", "true", "yes", "y", "sim")

                if len(cpf) != 11:
                    self.stderr.write(f"Line {i}: invalid CPF length after normalization: {cpf!r}")
                    errors += 1
                    continue

                first_name, last_name = split_first_last(raw_name)

                try:
                    user, was_created = User.objects.get_or_create(
                        cpf=cpf,
                        defaults={
                            "email": email,
                            "first_name": first_name,
                            "last_name": last_name,
                            "is_active": True,
                            "is_staff": False,
                            "is_superuser": False,
                        },
                    )

                    # Update base fields if not newly created
                    if not was_created:
                        user.email = email
                        user.first_name = first_name
                        user.last_name = last_name

                    # Password handling
                    if was_created or reset_passwords:
                        user.set_password(pw)

                    # Enforce "must change password" if the model supports it
                    if hasattr(user, "must_change_password") and force_change:
                        user.must_change_password = True

                    if dry_run:
                        skipped += 1
                        continue

                    user.save()

                    # Ensure group membership (Aluno) for both new and existing users
                    user.groups.add(alunos_group)

                    if was_created:
                        created += 1
                    else:
                        updated += 1

                except IntegrityError as e:
                    errors += 1
                    self.stderr.write(f"Line {i}: IntegrityError for CPF {cpf}: {e}")
                except Exception as e:
                    errors += 1
                    self.stderr.write(f"Line {i}: ERROR for CPF {cpf}: {e}")

        if dry_run:
            raise CommandError(
                f"DRY-RUN complete. Would create: {created}, update: {updated}, skip: {skipped}, errors: {errors}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created}, Updated: {updated}, Skipped: {skipped}, Errors: {errors}. "
                f"All users added to 'Aluno' group."
            )
        )
