from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.apps import apps as django_apps
from django.db import transaction

# The codenames we declared in Order.Meta.permissions
NEEDED_PERMS = [
    "can_view_kitchen",
    "can_manage_delivery",
    "can_view_orders",
]

class Command(BaseCommand):
    help = "Create default groups (Student, Staff) and attach fine-grained permissions for Hango."

    @transaction.atomic
    def handle(self, *args, **options):
        # Resolve the Order model by app label, avoiding hard imports
        try:
            Order = django_apps.get_model("orders", "Order")
        except LookupError:
            # Fallback: scan installed apps for an Order model that declares our permissions
            Order = None
            for config in django_apps.get_app_configs():
                try:
                    m = django_apps.get_model(config.label, "Order")
                except LookupError:
                    continue
                perms = getattr(m._meta, "permissions", []) or []
                codenames = {p[0] if isinstance(p, (list, tuple)) else p for p in perms}
                if set(NEEDED_PERMS).issubset(codenames):
                    Order = m
                    break
            if Order is None:
                raise CommandError(
                    "Could not locate the Order model. "
                    "Verify the app is installed in INSTALLED_APPS and that migrations ran."
                )

        # Ensure the Permission rows exist for this ContentType
        ct = ContentType.objects.get_for_model(Order)
        perms_qs = Permission.objects.filter(content_type=ct, codename__in=NEEDED_PERMS)
        perms_map = {p.codename: p for p in perms_qs}

        missing = [c for c in NEEDED_PERMS if c not in perms_map]
        if missing:
            raise CommandError(
                "Missing permissions for %s.%s: %s\n"
                "Run 'python manage.py makemigrations' and 'python manage.py migrate' after adding Meta.permissions."
                % (ct.app_label, ct.model, ", ".join(missing))
            )

        # Idempotent group creation
        student_group, _ = Group.objects.get_or_create(name="Student")
        staff_group, _ = Group.objects.get_or_create(name="Staff")

        # Attach required perms to Staff (additive)
        staff_group.permissions.add(*perms_map.values())
        staff_group.save()
        student_group.save()

        self.stdout.write(self.style.SUCCESS(
            "OK — groups seeded.\n"
            "  Student: no extra perms\n"
            "  Staff: %s" % ", ".join(sorted(perms_map))
        ))
