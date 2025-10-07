# apps/reports/admin.py
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import ReportsPorAluno, ReportsPorTurma

@admin.register(ReportsPorAluno)
class ReportsPorAlunoAdmin(admin.ModelAdmin):
    """
    Clicking this menu item sends the user straight to the existing
    'Por Aluno' filter view we added under Orders admin.
    """
    def changelist_view(self, request, extra_context=None):
        url = reverse("admin:orders_order_relatorio_por_aluno")
        return HttpResponseRedirect(url)

    # lock it down — we don't actually list or edit objects here
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(ReportsPorTurma)
class ReportsPorTurmaAdmin(admin.ModelAdmin):
    """
    Clicking this menu item sends the user straight to the existing
    'Por Turma' filter view we added under Orders admin.
    """
    def changelist_view(self, request, extra_context=None):
        url = reverse("admin:orders_order_relatorio_por_turma")
        return HttpResponseRedirect(url)

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
