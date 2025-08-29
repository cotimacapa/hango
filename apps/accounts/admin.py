# apps/accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User
from .forms import UserCreationForm, UserChangeForm

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    list_display = ("cpf", "first_name", "last_name", "is_staff", "is_active")
    ordering = ("cpf",)
    search_fields = ("cpf", "first_name", "last_name", "email")

    fieldsets = (
        (None, {"fields": ("cpf", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("cpf", "first_name", "last_name", "email", "password1", "password2",
                       "is_active", "is_staff", "is_superuser"),
        }),
    )
