# apps/accounts/models.py
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser, PermissionsMixin, BaseUserManager
)
from django.core.exceptions import ValidationError, PermissionDenied  # UPDATED
from django.utils import timezone  # NEW
from django.apps import apps        # NEW
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

    # ⬇️ NEW: Exigir troca de senha no próximo login (fluxo temporário)
    must_change_password = models.BooleanField(
        "Deve trocar a senha no próximo login",
        default=False,
        help_text="Se marcado, ao autenticar o usuário será redirecionado para definir uma nova senha."
    )

    # ⬇️ NOVOS CAMPOS: sobrescrita individual de dias de almoço
    lunch_days_override_enabled = models.BooleanField(
        "Ativar sobrescrita individual de dias de almoço",
        default=False,
        help_text="Se ativado, usa os dias individuais abaixo em vez das regras da turma.",
    )
    lunch_days_override_mask = models.PositiveSmallIntegerField(
        "Dias individuais de almoço",
        default=0,
        help_text="Bitmask dos dias permitidos: Seg=1, Ter=2, Qua=4, Qui=8, Sex=16, Sáb=32, Dom=64.",
    )

    # ⬇️ NEW: Bloqueio para pedidos / auditoria leve
    is_blocked = models.BooleanField("Bloqueado para pedir", default=False)  # NEW
    block_source = models.CharField(  # NEW
        "Origem do bloqueio",
        max_length=10,
        blank=True,
        choices=[("manual", "manual"), ("auto", "auto")],
    )
    blocked_reason = models.CharField("Motivo do bloqueio", max_length=200, blank=True)  # NEW
    blocked_at = models.DateTimeField("Data do bloqueio", null=True, blank=True)  # NEW
    blocked_by = models.ForeignKey(  # NEW
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blocks_made",
        verbose_name="Bloqueado por",
        limit_choices_to={"is_staff": True},
    )

    # ⬇️ NEW: Acompanhamento de faltas consecutivas (no-show)
    no_show_streak = models.PositiveSmallIntegerField("Faltas consecutivas", default=0)  # NEW
    last_no_show_at = models.DateField("Última falta", null=True, blank=True)  # NEW
    last_pickup_at = models.DateField("Última retirada", null=True, blank=True)  # NEW

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

    # ⬇️ NEW: API de bloqueio / desbloqueio
    def block(self, *, source: str, by=None, reason: str = "") -> None:
        """
        Bloqueia o usuário para fazer pedidos.
        source: "manual" | "auto"
        by: usuário staff que aplicou o bloqueio (ou None em auto)
        reason: texto curto (até 200 chars)
        """
        self.is_blocked = True
        self.block_source = source
        self.blocked_reason = (reason or "")[:200]
        self.blocked_at = timezone.now()
        self.blocked_by = by if (by and getattr(by, "is_staff", False)) else None

        # 🚀 Save *all* possibly changed fields including streak info
        self.save(
            update_fields=[
                "is_blocked",
                "block_source",
                "blocked_reason",
                "blocked_at",
                "blocked_by",
                "no_show_streak",
                "last_no_show_at",
            ]
        )

        # registrar evento
        BlockEvent = apps.get_model("accounts", "BlockEvent")
        BlockEvent.objects.create(
            user=self,
            action="block",
            source=source,
            by_user=self.blocked_by,
            reason=self.blocked_reason,
        )


    def unblock(self, *, by, reason: str = "") -> None:
        """
        Desbloqueia o usuário. Somente staff pode desbloquear.
        Regra: ao desbloquear manualmente, zera a sequência de faltas.
        """
        if not getattr(by, "is_staff", False):
            raise PermissionDenied("Apenas membros da equipe (staff) podem desbloquear.")

        self.is_blocked = False
        self.block_source = ""
        self.blocked_reason = (reason or "")[:200]
        self.blocked_at = None
        self.blocked_by = by
        self.no_show_streak = 0

        self.save(
            update_fields=[
                "is_blocked",
                "block_source",
                "blocked_reason",
                "blocked_at",
                "blocked_by",
                "no_show_streak",
            ]
        )

        BlockEvent = apps.get_model("accounts", "BlockEvent")
        BlockEvent.objects.create(
            user=self,
            action="unblock",
            source="manual",
            by_user=by,
            reason=self.blocked_reason,
        )


# ⬇️ NEW: trilha de auditoria de bloqueios/desbloqueios
class BlockEvent(models.Model):
    ACOES = [("block", "block"), ("unblock", "unblock")]
    FONTES = [("manual", "manual"), ("auto", "auto")]

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="block_events")
    action = models.CharField("Ação", max_length=8, choices=ACOES)
    source = models.CharField("Origem", max_length=8, choices=FONTES)
    by_user = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="block_events_made",
        verbose_name="Executado por",
    )
    reason = models.CharField("Motivo", max_length=200, blank=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Evento de bloqueio"
        verbose_name_plural = "Eventos de bloqueio"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.user} {self.action} ({self.source})"
