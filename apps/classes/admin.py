# apps/classes/admin.py
import re
from typing import Tuple

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html

from .models import StudentClass
from hango.admin.widgets import WeekdayMaskField  # bitmask widget for weekdays
from django.shortcuts import get_object_or_404, redirect, render

User = get_user_model()


# --------------------------- Form ---------------------------

class StudentClassAdminForm(forms.ModelForm):
    days_mask = WeekdayMaskField(
        label="Dias de almoço da turma",
        required=False,
        help_text="Selecione os dias em que a turma recebe almoço.",
    )

    # We'll populate the queryset in __init__ after we know the target year
    members = forms.ModelMultipleChoiceField(
        label="",
        required=False,
        queryset=User.objects.none(),
        widget=FilteredSelectMultiple("Alunos", is_stacked=False),
        help_text="",
    )

    class Meta:
        model = StudentClass
        fields = "__all__"

    # NEW: restrict "available" students to those NOT in another class of the same year
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        base_qs = (
            User.objects.filter(is_staff=False)
            .order_by("first_name", User.USERNAME_FIELD)
        )

        Membership = StudentClass.members.through

        # Figure out the target year:
        # - When editing: use instance.year
        # - When adding: try to read from posted/initial data (the "year" field)
        target_year = None
        if self.instance and getattr(self.instance, "pk", None):
            target_year = getattr(self.instance, "year", None)
        if target_year is None:
            ystr = (self.data.get("year") or self.initial.get("year") or "").strip()
            if ystr.isdigit():
                target_year = int(ystr)

        if target_year is not None:
            if self.instance and getattr(self.instance, "pk", None):
                # Editing: exclude users who already belong to another class in the SAME year,
                # but keep current members visible/selectable.
                busy_ids = (
                    Membership.objects
                    .filter(studentclass__year=target_year)
                    .exclude(studentclass_id=self.instance.pk)
                    .values_list("user_id", flat=True)
                    .distinct()
                )
            else:
                # Adding: exclude anyone who already belongs to any class in the SAME year
                busy_ids = (
                    Membership.objects
                    .filter(studentclass__year=target_year)
                    .values_list("user_id", flat=True)
                    .distinct()
                )
        else:
            # Fallback if we don't know the year yet (e.g., the year field hasn't been chosen):
            # hide students already assigned anywhere to avoid cross-assignment.
            busy_ids = (
                Membership.objects
                .values_list("user_id", flat=True)
                .distinct()
            )

        self.fields["members"].queryset = base_qs.exclude(pk__in=busy_ids)

    def clean_members(self):
        qs = self.cleaned_data.get("members")
        invalid = qs.filter(is_staff=True) | qs.filter(is_superuser=True)
        if invalid.exists():
            raise ValidationError("Apenas usuários não-staff podem ser membros.")
        return qs

    def clean_prev_year(self):
        prev = self.cleaned_data.get("prev_year")
        inst = self.instance

        if not prev:
            return prev

        if inst.pk and prev.pk == inst.pk:
            raise ValidationError("A turma anterior não pode ser a própria turma.")

        # Evita A -> B e B -> A
        try:
            if inst.pk and inst.next_year and inst.next_year.pk == prev.pk:
                raise ValidationError("Criaria um ciclo (a sucessora aponta para esta turma).")
        except ObjectDoesNotExist:
            pass

        # Garante que a turma anterior não tenha outra sucessora
        try:
            successor = prev.next_year
        except ObjectDoesNotExist:
            successor = None

        if successor and (not inst.pk or successor.pk != inst.pk):
            raise ValidationError("A turma anterior já possui outra sucessora.")

        return prev


# ------------------------ ModelAdmin ------------------------

@admin.register(StudentClass)
class StudentClassAdmin(admin.ModelAdmin):
    form = StudentClassAdminForm

    # List page
    list_display = ("name", "year", "is_active", "human_days", "member_count", "next_year_display")
    list_filter = ("year", "is_active")
    search_fields = (
        "name",
        f"members__{User.USERNAME_FIELD}",
        "members__first_name",
        "members__last_name",
    )
    actions = ["criar_sucessora", "migrar_alunos_do_ano_anterior"]

    # Custom change template (top-right buttons)
    change_form_template = "admin/classes/studentclass/change_form.html"

    # Allow prefill on Add via querystring (?name=...&year=...)
    def get_changeform_initial_data(self, request):
        allowed = {"name", "year"}
        return {k: v for k, v in request.GET.items() if k in allowed}

    # Provide extra context for template buttons (incl. new ROSTER button)
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        has_next_year = False
        next_year_url = None
        can_migrate_members = False
        migrate_members_url = None

        # NEW: roster button visibility + URL
        can_view_roster = False
        roster_url = None
        user_view_perm = f"{User._meta.app_label}.view_{User._meta.model_name}"

        if object_id:
            obj = self.get_object(request, object_id)
            if obj:
                # next-year info (hide/show create button)
                try:
                    nxt = obj.next_year
                except ObjectDoesNotExist:
                    nxt = None
                if nxt:
                    has_next_year = True
                    next_year_url = reverse("admin:classes_studentclass_change", args=[nxt.pk])

                # migrate button (only if prev_year exists)
                if obj.prev_year_id:
                    can_migrate_members = True
                    migrate_members_url = reverse(
                        "admin:classes_studentclass_migrate_members_from_prev",
                        args=[obj.pk],
                    )

                # NEW: roster button
                if self.has_view_permission(request, obj) and request.user.has_perm(user_view_perm):
                    can_view_roster = True
                    roster_url = reverse("admin:classes_studentclass_roster", args=[obj.pk])

        extra_context.update(
            {
                "has_next_year": has_next_year,
                "next_year_url": next_year_url,
                "can_migrate_members": can_migrate_members,
                "migrate_members_url": migrate_members_url,
                # NEW:
                "can_view_roster": can_view_roster,
                "roster_url": roster_url,
            }
        )
        return super().changeform_view(request, object_id, form_url, extra_context)

    # Form layout
    fieldsets = (
        ("Informações", {"fields": ("name", "year", "is_active", "days_mask")}),
        ("Vínculos de ano", {"fields": ("prev_year", "next_year_display")}),
        ("Membros", {"fields": ("members",)}),
    )
    readonly_fields = ("next_year_display",)

    # Column helpers / labels
    def member_count(self, obj: StudentClass) -> int:
        return obj.members.count()

    member_count.short_description = "Alunos"

    def next_year_display(self, obj: StudentClass):
        try:
            nxt = obj.next_year
        except ObjectDoesNotExist:
            nxt = None
        if not nxt:
            return "—"
        url = reverse("admin:classes_studentclass_change", args=[nxt.pk])
        return format_html('<a href="{}">{}</a>', url, nxt)

    next_year_display.short_description = "Próximo ano"

    # -------------------- name increment ---------------------

    @staticmethod
    def _guess_successor_name(current_name: str) -> str:
        s = current_name.strip()
        m = re.search(r"^(.*?)(\d+)\s*[º°oª]?\s*(?:ano)$", s, flags=re.IGNORECASE)
        if m:
            prefix = m.group(1).strip()
            n = int(m.group(2)) + 1
            return f"{prefix} {n}º Ano".strip()
        m2 = re.search(r"(.*?)(\d+)\s*$", s)
        if m2:
            prefix = m2.group(1).strip()
            n = int(m2.group(2)) + 1
            return f"{prefix} {n}".strip()
        return f"{s} — sequência"

    # ----------------- create/link successor -----------------

    def _find_or_create_successor(self, cls: StudentClass) -> Tuple[StudentClass, bool]:
        target_name = self._guess_successor_name(cls.name)
        expected_year = (cls.year + 1) if cls.year is not None else None

        with transaction.atomic():
            existing = StudentClass.objects.filter(name=target_name).first()
            if existing:
                if existing.prev_year_id and existing.prev_year_id != cls.id:
                    raise ValidationError(
                        f"Já existe a turma '{existing}' vinculada a outra anterior. "
                        "Ajuste manualmente se necessário."
                    )
                if existing.year is None and expected_year is not None:
                    existing.year = expected_year
                if not existing.days_mask:
                    existing.days_mask = cls.days_mask
                existing.prev_year = cls
                existing.save()
                return existing, False

            successor = StudentClass.objects.create(
                name=target_name,
                year=expected_year,
                is_active=True,
                days_mask=cls.days_mask,
                prev_year=cls,
            )
            return successor, True

    # ---------------------- extra URLs -----------------------

    def get_urls(self):
        urls = super().get_urls()
        my = [
            path(
                "<int:pk>/create_next_year/",
                self.admin_site.admin_view(self.create_next_year_view),
                name="classes_studentclass_create_next_year",
            ),
            path(
                "<int:pk>/migrate_members_from_prev/",
                self.admin_site.admin_view(self.migrate_members_from_prev_view),
                name="classes_studentclass_migrate_members_from_prev",
            ),
            # NEW: roster page (list of students)
            path(
                "<int:pk>/roster/",
                self.admin_site.admin_view(self.roster_view),
                name="classes_studentclass_roster",
            ),
        ]
        return my + urls

    # --------- migrate members from previous class -----------

    def _migrate_members_from_prev(self, cls: StudentClass) -> Tuple[int, int]:
        """
        Copy non-staff users from prev_year.members to cls.members.
        Returns (added_count, already_count).
        """
        if not cls.prev_year_id:
            raise ValidationError("Esta turma não possui ‘turma do ano anterior’.")

        prev = cls.prev_year
        source_qs = prev.members.filter(is_staff=False)
        target_ids = set(cls.members.values_list("id", flat=True))

        to_add = [u for u in source_qs if u.id not in target_ids]
        if to_add:
            cls.members.add(*to_add)

        return (len(to_add), source_qs.count() - len(to_add))

    def migrate_members_from_prev_view(self, request, pk):
        cls = get_object_or_404(StudentClass, pk=pk)
        try:
            added, already = self._migrate_members_from_prev(cls)
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
            return redirect(reverse("admin:classes_studentclass_change", args=[cls.pk]))

        if added:
            messages.success(request, f"Migrados {added} aluno(s) do ano anterior.")
        if already:
            messages.info(request, f"{already} já estavam nesta turma.")
        return redirect(reverse("admin:classes_studentclass_change", args=[cls.pk]))

    # ------------------- bulk actions ------------------------

    @admin.action(description="Criar turma sucessora (próximo ano)")
    def criar_sucessora(self, request, queryset):
        created, linked, skipped = 0, 0, 0
        for obj in queryset:
            try:
                _ = obj.next_year
                skipped += 1
                continue
            except ObjectDoesNotExist:
                pass

            try:
                successor, was_created = self._find_or_create_successor(obj)
            except ValidationError:
                skipped += 1
                continue

            if was_created:
                created += 1
            else:
                linked += 1

        if created:
            messages.success(request, f"Criadas {created} turma(s) sucessora(s).")
        if linked:
            messages.info(request, f"Vinculadas {linked} turma(s) sucessora(s) já existentes.")
        if skipped:
            messages.info(request, f"{skipped} turma(s) já possuíam sucessora ou foram ignoradas.")

    @admin.action(description="Migrar alunos do ano anterior para as turmas selecionadas")
    def migrar_alunos_do_ano_anterior(self, request, queryset):
        total_added = 0
        total_already = 0
        skipped = 0

        for cls in queryset:
            try:
                added, already = self._migrate_members_from_prev(cls)
            except ValidationError:
                skipped += 1
                continue
            total_added += added
            total_already += already

        if total_added:
            messages.success(request, f"Migrados {total_added} aluno(s) no total.")
        if total_already:
            messages.info(request, f"{total_already} já estavam nas turmas.")
        if skipped:
            messages.info(request, f"{skipped} turma(s) sem ‘ano anterior’ foram ignoradas.")

    # ----------------------- NEW: ROSTER ----------------------

    def roster_view(self, request, pk):
        """
        Read-only roster of students for a class.
        - Search by name/username/email (?q=)
        - Pagination (?page=)
        - CSV export (?format=csv)
        """
        cls = get_object_or_404(StudentClass, pk=pk)

        # Permissions: need to view the class AND view users
        user_view_perm = f"{User._meta.app_label}.view_{User._meta.model_name}"
        if not (self.has_view_permission(request, cls) and request.user.has_perm(user_view_perm)):
            raise PermissionDenied

        # Base queryset (non-staff only)
        qs = cls.members.filter(is_staff=False)

        # Search
        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(**{f"{User.USERNAME_FIELD}__icontains": q})
                | Q(email__icontains=q)
            )

        # Order: first_name, last_name, username
        qs = qs.only("first_name", "last_name", User.USERNAME_FIELD, "email").order_by(
            "first_name", "last_name", User.USERNAME_FIELD
        )

        # CSV export?
        if (request.GET.get("format") or "").lower() == "csv":
            resp = HttpResponse(content_type="text/csv; charset=utf-8")
            safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(cls.name or "turma"))
            resp["Content-Disposition"] = f'attachment; filename="turma_{safe_name}_{cls.year or ""}_alunos.csv"'
            import csv

            w = csv.writer(resp, lineterminator="\n")
            w.writerow(["nome_completo", "username", "email"])
            for u in qs:
                full = f"{u.first_name} {u.last_name}".strip() or str(u)
                username = getattr(u, User.USERNAME_FIELD, "")
                w.writerow([full, username, getattr(u, "email", "")])
            return resp

        # Pagination
        paginator = Paginator(qs, 50)
        page_obj = paginator.get_page(request.GET.get("page"))

        context = {
            "opts": self.model._meta,  # so the admin chrome renders correctly
            "title": f"Alunos — {cls}",
            "class_obj": cls,
            "count": paginator.count,
            "page_obj": page_obj,
            "paginator": paginator,
            "is_paginated": page_obj.has_other_pages(),
            "q": q,
        }
        return render(request, "admin/classes/studentclass/roster.html", context)

    def create_next_year_view(self, request, pk):
        cls = get_object_or_404(StudentClass, pk=pk)
        try:
            successor, created = self._find_or_create_successor(cls)
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
            return redirect(reverse("admin:classes_studentclass_change", args=[cls.pk]))

        if created:
            messages.success(request, f"Criada a turma sucessora: {successor}.")
        else:
            messages.info(request, f"Turma sucessora já existia; vínculo atualizado: {successor}.")

        return redirect(reverse("admin:classes_studentclass_change", args=[successor.pk]))
