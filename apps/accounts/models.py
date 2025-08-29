# apps/accounts/models.py
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, PermissionsMixin, BaseUserManager
)
from django.core.exceptions import ValidationError
import re


def validate_cpf(value: str):
    """Strict CPF validation (digits only + check digits)."""
    digits = re.sub(r'\D', '', value or '')
    if len(digits) != 11:
        raise ValidationError("CPF must have 11 digits.")
    if digits == digits[0] * 11:
        raise ValidationError("Invalid CPF.")
    s = sum(int(digits[i]) * (10 - i) for i in range(9))
    d1 = (s * 10) % 11
    d1 = 0 if d1 == 10 else d1
    if d1 != int(digits[9]):
        raise ValidationError("Invalid CPF.")
    s = sum(int(digits[i]) * (11 - i) for i in range(10))
    d2 = (s * 10) % 11
    d2 = 0 if d2 == 10 else d2
    if d2 != int(digits[10]):
        raise ValidationError("Invalid CPF.")


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, cpf, password, **extra):
        if not cpf:
            raise ValueError("CPF is required.")
        cpf = re.sub(r'\D', '', str(cpf))
        user = self.model(cpf=cpf, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, cpf, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(cpf, password, **extra)

    def create_superuser(self, cpf, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(cpf, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    cpf = models.CharField("CPF", max_length=11, unique=True, validators=[validate_cpf])
    first_name = models.CharField("first name", max_length=150, blank=True)
    last_name  = models.CharField("last name",  max_length=150, blank=True)
    email      = models.EmailField("email address", blank=True)

    is_active = models.BooleanField(default=True)
    is_staff  = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    # THIS makes CPF the login identifier
    USERNAME_FIELD = "cpf"
    REQUIRED_FIELDS: list[str] = []  # add "email" here if you want to require it

    objects = UserManager()

    def __str__(self):
        name = (self.first_name + " " + self.last_name).strip()
        return f"{self.cpf}{' — ' + name if name else ''}"
