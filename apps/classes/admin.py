from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import transaction
from django.shortcuts import redirect, get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from .models import StudentClass
from hango.admin.widgets import WeekdayMaskField  # your existing weekday bitmask widget

User = get_user_model()


class StudentClassAdminForm(forms.ModelForm):
    # Dias de almoço (bitmask)
    days_mask = WeekdayMaskField(
        label="Dias de almoço da turma",
        required=False,
        help_text="Selecione os dias em que a turma recebe almoço."
    )

    # Seletor de membros (alunos)
    members = forms.ModelMultipleChoiceField(
        label="",
        required=False,
        queryset=User.objects.filter(is_staff=False).order_by("first_name", User.USERNAME_FIELD),
        widget=FilteredSelectMultiple("Alunos", is_stacked=False),
        help_text="",
    )

    class Meta:
        model = StudentClass
        fields = "__all__"

    def clean_members(self):
        qs = self.cleaned_data.get("members")
        invalid = qs.filter(is_staff=True) | qs.filter(is_superuser=True)
        if invalid.exists():
            raise ValidationError("Apenas usuários não-staff podem ser membros.")
        return qs

    def clean_prev_year(self):
        """Previne ciclos e sucessora duplicada ao definir 'prev_year'."""
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


@admin.register(StudentClass)
class StudentClassAdmin(admin.ModelAdmin):
    form = StudentClassAdminForm

    # O que aparece na listagem
    list_display = ("name", "year", "is_active", "human_days", "member_count", "next_year")
    list_filter = ("year", "is_active")
    search_fields = (
        "name",
        f"members__{User.USERNAME_FIELD}",
        "members__first_name",
        "members__last_name",
    )

    # Template que injeta o botão "Criar sequência"
    change_form_template = "admin/classes/studentclass/change_form.html"

    # Permite prefills via querystring no Add
    def get_changeform_initial_data(self, request):
        allowed = {"name", "year"}
        return {k: v for k, v in request.GET.items() if k in allowed}

    # Campos no form
    fieldsets = (
        ("Informações", {"fields": ("name", "year", "is_active", "days_mask")}),
        # 'next_year' é relação reversa -> exibir apenas como leitura/link
        ("Vínculos de ano", {"fields": ("prev_year", "next_year_display"), "classes": ("collapse",)}),
        ("Membros", {"fields": ("members",)}),
    )
    readonly_fields = ("next_year_display",)

    # Contagem de membros para list_display
    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Alunos"

    # Exibe a sucessora como link somente leitura
    def next_year_display(self, obj):
        try:
            nxt = obj.next_year
        except ObjectDoesNotExist:
            nxt = None
        if not nxt:
            return "-"
        url = reverse("admin:classes_studentclass_change", args=[nxt.pk])
        return format_html('<a href="{}">{}</a>', url, nxt)
    next_year_display.short_description = "Próximo ano"

    # Endpoint usado pelo botão no change_form
    def get_urls(self):
        urls = super().get_urls()
        my = [
            path(
                "<int:pk>/create_next_year/",
                self.admin_site.admin_view(self.create_next_year_view),
                name="classes_studentclass_create_next_year",
            ),
        ]
        return my + urls

    def create_next_year_view(self, request, pk):
        cls = get_object_or_404(StudentClass, pk=pk)

        # Já tem sucessora?
        try:
            _ = cls.next_year
            messages.info(request, "Esta turma já possui uma sucessora.")
            return redirect(reverse("admin:classes_studentclass_change", args=[cls.pk]))
        except ObjectDoesNotExist:
            pass

        with transaction.atomic():
            successor = StudentClass.objects.create(
                name=cls.name,
                year=(cls.year + 1) if cls.year is not None else None,
                is_active=True,
                days_mask=cls.days_mask,
                prev_year=cls,  # define o vínculo; cria 'next_year' reverso
            )

        messages.success(
            request, f"Sequência criada: {successor} (vinculada como 'próximo ano')."
        )
        return redirect(reverse("admin:classes_studentclass_change", args=[cls.pk]))

    @admin.action(description="Criar turma sucessora (próximo ano)")
    def criar_sucessora(self, request, queryset):
        created, skipped = 0, 0
        for obj in queryset:
            # já tem sucessora?
            try:
                _ = obj.next_year
                skipped += 1
                continue
            except ObjectDoesNotExist:
                pass

            with transaction.atomic():
                StudentClass.objects.create(
                    name=obj.name,
                    year=(obj.year + 1) if obj.year is not None else None,
                    is_active=True,
                    days_mask=obj.days_mask,
                    prev_year=obj,
                )
                created += 1

        if created:
            messages.success(request, f"Criadas {created} turma(s) sucessora(s).")
        if skipped:
            messages.info(request, f"{skipped} turma(s) já possuíam sucessora e foram ignoradas.")
