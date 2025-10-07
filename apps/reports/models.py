# apps/reports/models.py
from apps.orders.models import Order

# Two proxy models (no DB tables). Each becomes its own menu item under the
# "Relatórios" section in the sidebar.

class ReportsPorAluno(Order):
    class Meta:
        proxy = True
        app_label = "reports"
        verbose_name = "Por Aluno"
        verbose_name_plural = "Por Aluno"


class ReportsPorTurma(Order):
    class Meta:
        proxy = True
        app_label = "reports"
        verbose_name = "Por Turma"
        verbose_name_plural = "Por Turma"
