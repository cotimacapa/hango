from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from .models import StudentClass

User = get_user_model()

class StudentClassAdminForm(forms.ModelForm):
    # Dual selector like Groups; hide the *outer* label to avoid the dangling "Alunos:"
    members = forms.ModelMultipleChoiceField(
        label="",  # ← hide outer label; widget headings still use the translated label below
        required=False,
        queryset=User.objects.filter(is_staff=False).order_by("first_name", User.USERNAME_FIELD),
        widget=FilteredSelectMultiple(_("Students"), is_stacked=False),
        help_text="",  # (optional) remove the long “Pressione Control…” help text
    )

    class Meta:
        model = StudentClass
        fields = "__all__"

    def clean_members(self):
        qs = self.cleaned_data.get("members")
        invalid = qs.filter(is_staff=True) | qs.filter(is_superuser=True)
        if invalid.exists():
            raise forms.ValidationError(_("Only non-staff users can be members."))
        return qs


@admin.register(StudentClass)
class StudentClassAdmin(admin.ModelAdmin):
    form = StudentClassAdminForm
    list_display = ("name", "member_count")
    search_fields = (
        "name",
        f"members__{User.USERNAME_FIELD}",
        "members__first_name",
        "members__last_name",
    )
