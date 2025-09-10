# apps/accounts/admin.py
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User
from .forms import UserCreationForm, UserChangeForm
from hango.admin.widgets import WeekdayMaskField


class UserAdminForm(UserChangeForm):
    # Checkboxes Seg..Dom → bitmask
    lunch_days_override_mask = WeekdayMaskField(
        label="Dias individuais de almoço",
        required=False,
        help_text="Usado somente quando a sobrescrita está ativada."
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        # Para contas de staff, ocultar os campos de sobrescrita (não se aplicam)
        if instance and instance.is_staff:
            self.fields["lunch_days_override_enabled"].widget = forms.HiddenInput()
            self.fields["lunch_days_override_mask"].widget = forms.HiddenInput()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserAdminForm  # <-- usar o form com WeekdayMaskField
    model = User

    list_display = ("cpf", "first_name", "last_name", "is_staff", "is_active", "human_lunch_days_override")
    ordering = ("cpf",)
    search_fields = ("cpf", "first_name", "last_name", "email")

    fieldsets = (
        (None, {"fields": ("cpf", "password")}),
        ("Informações pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Almoço", {"fields": ("lunch_days_override_enabled", "lunch_days_override_mask")}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas importantes", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "cpf", "first_name", "last_name", "email",
                "password1", "password2",
                "is_active", "is_staff", "is_superuser",
            ),
        }),
    )
