# apps/accounts/forms.py
from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.core.exceptions import ValidationError
from .models import User
import re


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Senha", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirme a senha", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("cpf", "first_name", "last_name", "email")

    def clean_cpf(self):
        # Normaliza para apenas dígitos (evita colisões por pontuação)
        cpf = re.sub(r"\D", "", self.cleaned_data["cpf"])
        return cpf

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "As senhas não coincidem.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="Senha")

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
        # Normaliza CPF para dígitos; não força revalidação pesada se inalterado
        cpf = re.sub(r"\D", "", self.cleaned_data.get("cpf", "") or "")
        return cpf

    def clean(self):
        """
        Torna o formulário imune a validações indevidas quando o usuário é staff:
        - Campos de sobrescrita de almoço ficam opcionais e são coeridos para defaults.
        - Se não for staff e a sobrescrita estiver ligada, exige uma máscara não nula.
        """
        cleaned = super().clean()

        # Descobre o valor efetivo de is_staff no POST (ou mantém do instance)
        is_staff_post = cleaned.get("is_staff")
        is_staff_effective = bool(is_staff_post if is_staff_post is not None else getattr(self.instance, "is_staff", False))

        # Garanta que os campos existam no form (caso alguma customização os oculte)
        if "lunch_days_override_enabled" in self.fields:
            self.fields["lunch_days_override_enabled"].required = False
        if "lunch_days_override_mask" in self.fields:
            self.fields["lunch_days_override_mask"].required = False

        if is_staff_effective:
            # Operadores não usam sobrescrita; força defaults silenciosamente
            cleaned["lunch_days_override_enabled"] = False
            cleaned["lunch_days_override_mask"] = 0
            # Reflete em cleaned_data para que o admin salve sem reclamar
            self.cleaned_data["lunch_days_override_enabled"] = False
            self.cleaned_data["lunch_days_override_mask"] = 0
        else:
            # Para estudantes: se ligar a sobrescrita, precisa de uma máscara > 0
            if cleaned.get("lunch_days_override_enabled"):
                mask = int(cleaned.get("lunch_days_override_mask") or 0)
                if mask <= 0:
                    self.add_error("lunch_days_override_mask", "Selecione ao menos um dia da semana.")

        return cleaned
