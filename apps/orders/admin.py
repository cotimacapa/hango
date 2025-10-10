# apps/orders/admin.py
from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from django.db.models import Count, Q
from django.template.response import TemplateResponse
from django.urls import path
from django.contrib.auth import get_user_model
from django.http import JsonResponse
import re
from functools import reduce
import operator

from .models import Order, OrderItem
from apps.orders.services import mark_no_show, mark_picked_up

from .forms import RelatorioPorAlunoForm, RelatorioPorTurmaForm
from apps.classes.models import StudentClass


# ---------- helpers for "Histórico detalhado" ----------
def _status_labels(order):
    """Human strings for the appendix."""
    st = "Cancelado" if order.status == "canceled" else "Ativo"
    ent = (
        "Entregue" if order.delivery_status == "delivered"
        else "Não entregue" if order.delivery_status == "undelivered"
        else "—"
    )
    return st, ent


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ("item",)
    fields = ("item", "qty")
    verbose_name = "Item"
    verbose_name_plural = "Itens"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    date_hierarchy = "service_day"
    ordering = ("-created_at",)
    list_select_related = ("user", "delivered_by")

    list_display = (
        "id",
        "user",
        "pickup_token",
        "user_blocked",
        "user_no_show_streak",
        "service_day",
        "status",
        "delivery_status",
        "created_at",
        "delivered_at",
        "delivered_by",
    )
    list_filter = (
        "status",
        "delivery_status",
        ("service_day", admin.DateFieldListFilter),
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "pickup_token",
        "user__cpf",
        "user__first_name",
        "user__last_name",
    )
    readonly_fields = ("created_at", "pickup_token")
    fields = (
        ("user", "service_day"),
        ("status", "delivery_status"),
        ("created_at", "pickup_token"),
        ("delivered_at", "delivered_by"),
    )
    save_on_top = True

    @admin.display(boolean=True, description="Bloq.")
    def user_blocked(self, obj: Order) -> bool:
        return bool(getattr(obj.user, "is_blocked", False))

    @admin.display(description="Faltas seguidas")
    def user_no_show_streak(self, obj: Order) -> int:
        return int(getattr(obj.user, "no_show_streak", 0))

    @admin.action(description="Marcar como retirado")
    def action_mark_picked_up(self, request, queryset):
        count = 0
        for order in queryset:
            mark_picked_up(order, by=request.user)
            count += 1
        if count:
            messages.success(request, _(f"{count} pedido(s) marcados como retirado."))

    @admin.action(description="Marcar como falta (no-show)")
    def action_mark_no_show(self, request, queryset):
        count = 0
        for order in queryset:
            mark_no_show(order)
            count += 1
        if count:
            messages.success(request, _(f"{count} pedido(s) marcados como não entregue (falta)."))

    actions = ("action_mark_picked_up", "action_mark_no_show")

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            return {}
        return actions

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user", "delivered_by").prefetch_related("lines__item")

    # -------------------------- URLs --------------------------
    def get_urls(self):
        urls = super().get_urls()
        extra = [
            # live student search endpoint (type-ahead)
            path(
                "relatorios/search-alunos/",
                self.admin_site.admin_view(self.search_alunos),
                name="orders_order_relatorios_search_alunos",
            ),
            path(
                "relatorios/por-aluno/",
                self.admin_site.admin_view(self.relatorio_por_aluno),
                name="orders_order_relatorio_por_aluno",
            ),
            path(
                "relatorios/por-turma/",
                self.admin_site.admin_view(self.relatorio_por_turma),
                name="orders_order_relatorio_por_turma",
            ),
        ]
        return extra + urls

    # -------------------------- LIVE SEARCH --------------------------
    def _filter_students_queryset(self, turma_id=None):
        """Base queryset for student users, optionally restricted to a class."""
        User = get_user_model()
        qs = User.objects.filter(is_staff=False, groups__name="Aluno")
        if turma_id:
            turma = StudentClass.objects.filter(pk=turma_id).first()
            if turma:
                qs = qs.filter(pk__in=turma.members.values("pk"))
        return qs

    def search_alunos(self, request):
        """
        JSON: /admin/orders/order/relatorios/search-alunos/?q=...&turma_id=...
        Returns up to 8 matches by name or CPF.
        """
        q = (request.GET.get("q") or "").strip()
        turma_id = request.GET.get("turma_id") or None

        if not q:
            return JsonResponse({"results": []})

        qs = self._filter_students_queryset(turma_id=turma_id)
        tokens = [t for t in re.split(r"\s+", q) if t]

        def _tok_to_q(tok):
            cpf_tok = re.sub(r"\D+", "", tok)
            qobj = Q(first_name__icontains=tok) | Q(last_name__icontains=tok)
            if cpf_tok:
                qobj |= Q(cpf__icontains=cpf_tok)
            return qobj

        combined = reduce(operator.and_, (_tok_to_q(t) for t in tokens))
        qs = qs.filter(combined).order_by("first_name", "last_name")[:8]

        results = [
            {
                "id": u.id,
                "label": f"{u.get_full_name()} — {getattr(u, 'cpf', '') or ''}".strip(" —"),
            }
            for u in qs
        ]
        return JsonResponse({"results": results})

    # -------------------------- Reports --------------------------
    def relatorio_por_aluno(self, request):
        form = RelatorioPorAlunoForm(request.GET or None)
        if not form.is_valid():
            ctx = {"form": form, "title": "Relatórios → Por Aluno"}
            return TemplateResponse(
                request,
                "admin/orders/relatorios_por_aluno_filter.html",
                ctx,
            )

        data = form.cleaned_data
        periodo = data["periodo_resolvido"]
        incluir_cancelados = data.get("incluir_cancelados", False)
        incluir_historico = data.get("incluir_historico", False)  # NEW
        apenas_entregues = data.get("apenas_entregues", False)    # safe if removed in form
        incluir_sem_pedidos = data.get("incluir_sem_pedidos", False)
        buscar = data.get("buscar") or ""
        turma = data.get("turma")

        # selected student from type-ahead
        aluno_id = request.GET.get("aluno_id")
        try:
            aluno_id = int(aluno_id) if aluno_id else None
        except (TypeError, ValueError):
            aluno_id = None

        User = get_user_model()
        users_qs = self._filter_students_queryset(turma_id=turma.pk if turma else None)

        if aluno_id:
            users_qs = users_qs.filter(pk=aluno_id)
        elif buscar:
            users_qs = users_qs.filter(
                Q(first_name__icontains=buscar) |
                Q(last_name__icontains=buscar) |
                Q(cpf__icontains=re.sub(r"\D+", "", buscar))
            )

        orders = Order.objects.filter(service_day__range=(periodo.inicio, periodo.fim))
        if not incluir_cancelados:
            orders = orders.exclude(status="canceled")

        agg = orders.values("user_id").annotate(
            total=Count("id"),
            entregues=Count("id", filter=Q(delivery_status="delivered")),
            nao_entregue=Count("id", filter=Q(delivery_status="undelivered") & ~Q(status="canceled")),
            cancelados=Count("id", filter=Q(status="canceled")),
        )
        agg_map = {row["user_id"]: row for row in agg}

        if not aluno_id and turma is None and not buscar and not incluir_sem_pedidos:
            user_ids_with_orders = list(agg_map.keys())
            users_qs = users_qs.filter(id__in=user_ids_with_orders)

        rows = []
        for u in users_qs:
            stats = agg_map.get(u.id, {"total": 0, "entregues": 0, "nao_entregue": 0, "cancelados": 0})
            if not incluir_sem_pedidos and stats["total"] == 0:
                continue
            total_display = stats["entregues"] if apenas_entregues else stats["total"]
            rows.append(
                {
                    "uid": u.id,  # NEW: for appendix map
                    "nome": u.get_full_name() or str(u),
                    "cpf": getattr(u, "cpf", "") or "",
                    "total": total_display,
                    "entregues": stats["entregues"],
                    "nao_entregue": stats["nao_entregue"],
                    "cancelados": stats["cancelados"],
                }
            )

        # attach detailed history if requested
        if incluir_historico and rows:
            by_uid = {r["uid"]: r for r in rows}
            hist_orders = Order.objects.filter(
                service_day__range=(periodo.inicio, periodo.fim),
                user_id__in=by_uid.keys(),
            ).only("user_id", "service_day", "status", "delivery_status").order_by("service_day")
            if not incluir_cancelados:
                hist_orders = hist_orders.exclude(status="canceled")
            for o in hist_orders:
                st, ent = _status_labels(o)
                by_uid[o.user_id].setdefault("historico", []).append({
                    "data": o.service_day,
                    "status": st,
                    "entrega": ent,
                })

        sum_total = sum(r["total"] for r in rows)
        sum_entregues = sum(r["entregues"] for r in rows)
        sum_nao_entregue = sum(r["nao_entregue"] for r in rows)
        sum_cancelados = sum(r["cancelados"] for r in rows)

        ctx = {
            "title": "Relatórios → Por Aluno (Resumo)",
            "periodo": periodo,
            "incluir_cancelados": incluir_cancelados,
            "incluir_historico": incluir_historico,  # NEW
            "apenas_entregues": apenas_entregues,
            "rows": rows,
            "sum_total": sum_total,
            "sum_entregues": sum_entregues,
            "sum_nao_entregue": sum_nao_entregue,
            "sum_cancelados": sum_cancelados,
        }
        return TemplateResponse(
            request,
            "admin/orders/relatorios_por_aluno_report.html",
            ctx,
        )

    def relatorio_por_turma(self, request):
        form = RelatorioPorTurmaForm(request.GET or None)
        if not form.is_valid() or "__filter__" in request.GET:
            ctx = {"form": form, "title": "Relatórios → Por Turma"}
            return TemplateResponse(
                request,
                "admin/orders/relatorios_por_turma_filter.html",
                ctx,
            )

        data = form.cleaned_data
        periodo = data["periodo_resolvido"]
        incluir_cancelados = data.get("incluir_cancelados", False)
        incluir_historico = data.get("incluir_historico", False)  # NEW
        apenas_entregues = data.get("apenas_entregues", False)
        incluir_sem_pedidos = data.get("incluir_sem_pedidos", False)
        buscar = data.get("buscar") or ""
        turma = data.get("turma")

        # toggle inativas: if no class chosen, switch all active vs all classes
        show_inactive = data.get("mostrar_inativas", False)
        if turma is not None:
            turmas_qs = StudentClass.objects.filter(pk=turma.pk)
        else:
            turmas_qs = StudentClass.objects.all() if show_inactive else StudentClass.objects.filter(is_active=True)

        orders = Order.objects.filter(service_day__range=(periodo.inicio, periodo.fim))
        if not incluir_cancelados:
            orders = orders.exclude(status="canceled")

        agg = orders.values("user_id").annotate(
            total=Count("id"),
            entregues=Count("id", filter=Q(delivery_status="delivered")),
            nao_entregue=Count("id", filter=Q(delivery_status="undelivered") & ~Q(status="canceled")),
            cancelados=Count("id", filter=Q(status="canceled")),
        )
        agg_map = {row["user_id"]: row for row in agg}

        sections = []
        for turma in turmas_qs:
            alunos_qs = turma.members.filter(is_staff=False, groups__name="Aluno")
            if buscar:
                alunos_qs = alunos_qs.filter(
                    Q(first_name__icontains=buscar) |
                    Q(last_name__icontains=buscar) |
                    Q(cpf__icontains=re.sub(r"\D+", "", buscar))
                )

            rows = []
            for u in alunos_qs:
                stats = agg_map.get(u.id, {"total": 0, "entregues": 0, "nao_entregue": 0, "cancelados": 0})
                if not incluir_sem_pedidos and stats["total"] == 0:
                    continue
                total_display = stats["entregues"] if apenas_entregues else stats["total"]
                rows.append(
                    {
                        "uid": u.id,  # NEW
                        "nome": u.get_full_name() or str(u),
                        "cpf": getattr(u, "cpf", "") or "",
                        "total": total_display,
                        "entregues": stats["entregues"],
                        "nao_entregue": stats["nao_entregue"],
                        "cancelados": stats["cancelados"],
                    }
                )

            sec_totals = {
                "total": sum(r["total"] for r in rows),
                "entregues": sum(r["entregues"] for r in rows),
                "nao_entregue": sum(r["nao_entregue"] for r in rows),
                "cancelados": sum(r["cancelados"] for r in rows),
            }
            sections.append({"turma": turma, "rows": rows, "totals": sec_totals})

        # attach detailed history if requested
        if incluir_historico and sections:
            # map uid -> row dict across all sections
            by_uid = {}
            for sec in sections:
                for r in sec["rows"]:
                    by_uid[r["uid"]] = r

            hist_orders = Order.objects.filter(
                service_day__range=(periodo.inicio, periodo.fim),
                user_id__in=by_uid.keys(),
            ).only("user_id", "service_day", "status", "delivery_status").order_by("service_day")
            if not incluir_cancelados:
                hist_orders = hist_orders.exclude(status="canceled")
            for o in hist_orders:
                st, ent = _status_labels(o)
                by_uid[o.user_id].setdefault("historico", []).append({
                    "data": o.service_day,
                    "status": st,
                    "entrega": ent,
                })

        grand_totals = {
            "total": sum(sec["totals"]["total"] for sec in sections),
            "entregues": sum(sec["totals"]["entregues"] for sec in sections),
            "nao_entregue": sum(sec["totals"]["nao_entregue"] for sec in sections),
            "cancelados": sum(sec["totals"]["cancelados"] for sec in sections),
        }

        ctx = {
            "title": "Relatórios → Por Turma (Resumo)",
            "periodo": periodo,
            "incluir_cancelados": incluir_cancelados,
            "incluir_historico": incluir_historico,  # NEW
            "apenas_entregues": apenas_entregues,
            "sections": sections,
            "grand_totals": grand_totals,
        }
        return TemplateResponse(
            request,
            "admin/orders/relatorios_por_turma_report.html",
            ctx,
        )
    
        # PAGINATION
    list_per_page = 25            # how many Pedidos per page
    list_max_show_all = 2000      # cap for “Show all”
    show_full_result_count = False  # skip COUNT(*) on large tables = faster pages

    # Optional: quality of life
    # actions_on_top = True
    # actions_on_bottom = True


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "item", "qty")
    list_select_related = ("order", "item")
    search_fields = ("order__id", "item__name", "order__user__cpf")
    list_filter = (("order__service_day", admin.DateFieldListFilter),)
    autocomplete_fields = ("order", "item")

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
