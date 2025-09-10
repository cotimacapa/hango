# apps/accounts/forms.py
from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from .models import User
import re


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Senha", widget=forms.PasswordInput)  # UPDATED
    password2 = forms.CharField(label="Confirme a senha", widget=forms.PasswordInput)  # UPDATED

    class Meta:
        model = User
        fields = ("cpf", "first_name", "last_name", "email")

    def clean_cpf(self):
        cpf = re.sub(r"\D", "", self.cleaned_data["cpf"])
        return cpf

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "As senhas não coincidem.")  # UPDATED
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="Senha")  # UPDATED

    class Meta:
        model = User
        fields = (
            "cpf", "first_name", "last_name", "email", "password",
            "is_active", "is_staff", "is_superuser", "groups", "user_permissions",
            "lunch_days_override_enabled",
            "lunch_days_override_mask",
        )
        labels = {
            "lunch_days_override_enabled": "Ativar sobrescrita individual de dias de almoço",
            "lunch_days_override_mask": "Dias individuais de almoço",
        }
        help_texts = {
            "lunch_days_override_enabled": "Se ativado, usa os dias individuais abaixo em vez das regras da turma.",
            "lunch_days_override_mask": "Bitmask: Seg=1, Ter=2, Qua=4, Qui=8, Sex=16, Sáb=32, Dom=64.",
        }

    def clean_cpf(self):
        cpf = re.sub(r"\D", "", self.cleaned_data.get("cpf", ""))
        return cpf
