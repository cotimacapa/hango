# apps/orders/forms.py
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.classes.models import StudentClass


# ----------------- Checkout (mantido) -----------------

class CheckoutForm(forms.Form):
    pickup_slot = forms.DateTimeField(required=False, help_text="Optional pickup time")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        user = getattr(self, "user", None)

        if user is None:
            return cleaned

        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            raise ValidationError("Operadores não podem realizar pedidos.")

        if getattr(user, "is_blocked", False):
            raise ValidationError("Seu usuário está bloqueado para fazer pedidos. Procure a equipe.")

        return cleaned


# --------------- Relatórios: base de período ---------------

class PeriodoPreset:
    VAZIO = ""
    MES_PASSADO = "MES_PASSADO"
    ULT_6_MESES = "ULT_6_MESES"
    ULTIMO_ANO = "ULTIMO_ANO"

    CHOICES = (
        (VAZIO, "Customizado (entre datas)"),
        (MES_PASSADO, "Mês passado (1º ao último dia)"),
        (ULT_6_MESES, "Últimos 6 meses (calendáricos)"),
        (ULTIMO_ANO, "Último ano (12 meses calendáricos)"),
    )


@dataclass
class PeriodoResolvido:
    inicio: date
    fim: date


def _primeiro_dia_do_mes(d: date) -> date:
    return d.replace(day=1)


def _ultimo_dia_do_mes(d: date) -> date:
    last_day = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=last_day)


def _adicionar_meses(d: date, delta_meses: int) -> date:
    y = d.year + (d.month - 1 + delta_meses) // 12
    m = (d.month - 1 + delta_meses) % 12 + 1
    last = calendar.monthrange(y, m)[1]
    day = min(d.day, last)
    return date(y, m, day)


class BaseRelatorioPeriodoForm(forms.Form):
    preset = forms.ChoiceField(
        label="Período rápido",
        choices=PeriodoPreset.CHOICES,
        required=False,
        initial=PeriodoPreset.MES_PASSADO,
        help_text="Escolha um atalho de período ou deixe em 'Customizado' e informe as datas.",
    )
    data_inicio = forms.DateField(
        label="Início",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    data_fim = forms.DateField(
        label="Fim",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    incluir_cancelados = forms.BooleanField(
        label="Incluir cancelados",
        required=False,
        initial=False,
    )
    apenas_entregues = forms.BooleanField(  # será removido nas telas específicas
        label="Contar apenas entregues (no Resumo)",
        required=False,
        initial=False,
    )
    incluir_historico = forms.BooleanField(
        label="Incluir histórico detalhado",
        required=False,
        initial=False,
        help_text="Quando marcado, a versão para impressão mostrará a lista completa dos pedidos.",
    )

    buscar = forms.CharField(  # será removido nas telas específicas
        label="Buscar por nome ou CPF",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Nome ou CPF"}),
    )

    def clean(self):
        cleaned = super().clean()

        preset = cleaned.get("preset") or ""
        di = cleaned.get("data_inicio")
        df = cleaned.get("data_fim")

        hoje = timezone.localdate()

        if preset == PeriodoPreset.MES_PASSADO:
            base = _primeiro_dia_do_mes(hoje)
            inicio = _primeiro_dia_do_mes(_adicionar_meses(base, -1))
            fim = _ultimo_dia_do_mes(_adicionar_meses(base, -1))
        elif preset == PeriodoPreset.ULT_6_MESES:
            inicio = _primeiro_dia_do_mes(_adicionar_meses(hoje, -5))
            fim = _ultimo_dia_do_mes(hoje)
        elif preset == PeriodoPreset.ULTIMO_ANO:
            inicio = _primeiro_dia_do_mes(_adicionar_meses(hoje, -11))
            fim = _ultimo_dia_do_mes(hoje)
        else:
            if not di or not df:
                raise ValidationError("Informe 'Início' e 'Fim' ou escolha um período rápido.")
            inicio, fim = di, df

        if inicio > fim:
            raise ValidationError("A data inicial não pode ser posterior à data final.")

        cleaned["periodo_resolvido"] = PeriodoResolvido(inicio=inicio, fim=fim)
        return cleaned


# --------------- Relatórios: forms específicos ---------------

class RelatorioPorAlunoForm(BaseRelatorioPeriodoForm):
    """
    Relatórios → Por Aluno
    - No class filters here (clean, student-first).
    """
    incluir_sem_pedidos = forms.BooleanField(
        label="Incluir alunos sem pedidos",
        required=False,
        initial=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Remove fields that don't belong here
        for name in ("buscar", "apenas_entregues", "mostrar_inativas", "turma"):
            self.fields.pop(name, None)

        # Natural field order for this page
        self.order_fields([
            "preset", "data_inicio", "data_fim",
            "incluir_historico",
            "incluir_cancelados",
            "incluir_sem_pedidos",
        ])


class RelatorioPorTurmaForm(BaseRelatorioPeriodoForm):
    """
    Filters for Relatórios → Por Turma.

    - Drop the inherited name/CPF search and 'apenas_entregues'.
    - Single class selection via regular dropdown.
    """
    mostrar_inativas = forms.BooleanField(
        label="Mostrar turmas inativas",
        required=False,
        initial=False,
    )

    turma = forms.ModelChoiceField(
        label="Turma",
        queryset=StudentClass.objects.none(),   # set in __init__
        required=False,
        empty_label="(todas as turmas ativas)",
    )

    incluir_sem_pedidos = forms.BooleanField(
        label="Incluir alunos sem pedidos",
        required=False,
        initial=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Remove the name/CPF search and the confusing 'apenas_entregues'
        self.fields.pop("buscar", None)
        self.fields.pop("apenas_entregues", None)

        # Build the queryset (active by default; include inactive if toggled)
        data = getattr(self, "data", None)
        show_inactive = False
        if data:
            show_inactive = data.get("mostrar_inativas") in ("on", "true", "True", "1")
        elif self.initial:
            show_inactive = bool(self.initial.get("mostrar_inativas"))

        if show_inactive:
            qs = StudentClass.objects.all().order_by("name")
        else:
            qs = StudentClass.objects.filter(is_active=True).order_by("name")

        self.fields["turma"].queryset = qs

        # ← NEW: flip empty label to reflect inactive toggle
        self.fields["turma"].empty_label = "(todas as turmas)" if show_inactive else "(todas as turmas ativas)"

        # Field order for a clearer flow
        self.order_fields([
            "preset", "data_inicio", "data_fim",
            "incluir_historico", "mostrar_inativas", "turma",
            "incluir_cancelados", "incluir_sem_pedidos",
        ])
