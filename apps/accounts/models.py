# apps/accounts/models.py
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, PermissionsMixin, BaseUserManager
)
from django.core.exceptions import ValidationError
import re

# ⬇️ Import para exibir dias de almoço de forma legível
from hango.core.weekdays import human_days as human_days_str


def validate_cpf(value: str):
    """Validação estrita de CPF (apenas dígitos + dígitos verificadores)."""
    digits = re.sub(r'\D', '', value or '')
    if len(digits) != 11:
        raise ValidationError("O CPF deve ter 11 dígitos.")
    if digits == digits[0] * 11:
        raise ValidationError("CPF inválido.")
    s = sum(int(digits[i]) * (10 - i) for i in range(9))
    d1 = (s * 10) % 11
    d1 = 0 if d1 == 10 else d1
    if d1 != int(digits[9]):
        raise ValidationError("CPF inválido.")
    s = sum(int(digits[i]) * (11 - i) for i in range(10))
    d2 = (s * 10) % 11
    d2 = 0 if d2 == 10 else d2
    if d2 != int(digits[10]):
        raise ValidationError("CPF inválido.")


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, cpf, password, **extra):
        if not cpf:
            raise ValueError("O CPF é obrigatório.")
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
            raise ValueError("O superusuário deve ter is_staff=True e is_superuser=True.")
        return self._create_user(cpf, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    cpf        = models.CharField("CPF", max_length=11, unique=True, validators=[validate_cpf])
    first_name = models.CharField("Nome", max_length=150, blank=True)
    last_name  = models.CharField("Sobrenome", max_length=150, blank=True)
    email      = models.EmailField("E-mail", blank=True)

    is_active  = models.BooleanField("Ativo", default=True)
    is_staff   = models.BooleanField("Equipe/Staff", default=False)
    date_joined = models.DateTimeField("Data de cadastro", auto_now_add=True)

    # ⬇️ NOVOS CAMPOS: sobrescrita individual de dias de almoço
    lunch_days_override_enabled = models.BooleanField(
        "Ativar sobrescrita individual de dias de almoço",
        default=False,
        help_text="Se ativado, usa os dias individuais abaixo em vez das regras da turma.",
    )
    lunch_days_override_mask = models.PositiveSmallIntegerField(
        "Dias individuais de almoço (Seg–Dom)",
        default=0,
        help_text="Bitmask dos dias permitidos: Seg=1, Ter=2, Qua=4, Qui=8, Sex=16, Sáb=32, Dom=64.",
    )

    # CPF é o identificador de login
    USERNAME_FIELD = "cpf"
    REQUIRED_FIELDS: list[str] = ["first_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    # ---- Exibição amigável ----
    def get_full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.cpf

    def get_short_name(self) -> str:
        return self.first_name or self.cpf

    @property
    def username(self) -> str:
        """Compatibilidade para código/templates que esperam .username."""
        return self.cpf

    def __str__(self) -> str:
        return self.get_full_name()

    # ⬇️ NOVO: auxiliar para exibir no admin
    def human_lunch_days_override(self) -> str:
        if not self.lunch_days_override_enabled:
            return "—"
        return human_days_str(self.lunch_days_override_mask)
    human_lunch_days_override.short_description = "Dias (sobrescrita)"
