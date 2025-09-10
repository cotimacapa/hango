from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth import get_user_model

from .models import StudentClass
from hango.admin.widgets import WeekdayMaskField

User = get_user_model()


class StudentClassAdminForm(forms.ModelForm):
    # Checkboxes Seg..Dom → bitmask
    days_mask = WeekdayMaskField(
        label="Dias de almoço da turma",
        required=False,
        help_text="Selecione os dias em que a turma recebe almoço."
    )

    # Dual selector (tipo Grupos); esconder o rótulo externo para evitar “Alunos:” solto
    members = forms.ModelMultipleChoiceField(
        label="",  # rótulo externo vazio; o widget usa o título abaixo
        required=False,
        queryset=User.objects.filter(is_staff=False).order_by("first_name", User.USERNAME_FIELD),
        widget=FilteredSelectMultiple("Alunos", is_stacked=False),
        help_text="",  # (opcional) remover o help padrão “Pressione Control…”
    )

    class Meta:
        model = StudentClass
        fields = "__all__"

    def clean_members(self):
        qs = self.cleaned_data.get("members")
        invalid = qs.filter(is_staff=True) | qs.filter(is_superuser=True)
        if invalid.exists():
            raise forms.ValidationError("Apenas usuários não-staff podem ser membros.")
        return qs


@admin.register(StudentClass)
class StudentClassAdmin(admin.ModelAdmin):
    form = StudentClassAdminForm
    list_display = ("name", "human_days", "member_count")
    search_fields = (
        "name",
        f"members__{User.USERNAME_FIELD}",
        "members__first_name",
        "members__last_name",
    )
