# apps/accounts/forms.py
from django import forms
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from .models import User
import re

class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Password (again)", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("cpf", "first_name", "last_name", "email")

    def clean_cpf(self):
        cpf = re.sub(r"\D", "", self.cleaned_data["cpf"])
        return cpf

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Passwords don’t match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="Password")

    class Meta:
        model = User
        fields = ("cpf", "first_name", "last_name", "email", "password",
                  "is_active", "is_staff", "is_superuser", "groups", "user_permissions")
