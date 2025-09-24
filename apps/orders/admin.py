# apps/orders/admin.py
from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings
from django.http import HttpResponse
from django.template.response import TemplateResponse

import csv
from datetime import timedelta, date
from collections import Counter

from .models import Order, OrderItem
from apps.orders.services import mark_no_show, mark_picked_up

# Closures (Dias sem atendimento)
try:
    from apps.calendar.models import DiaSemAtendimento
except Exception:  # calendar app may not be installed yet in some envs
    DiaSemAtendimento = None


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

    # Columns
    list_display = (
        "id",
        "user",
        "pickup_token",    # NEW: mostra o token
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
    search_fields = ("pickup_token", "user__cpf", "user__first_name", "user__last_name")  # NEW
    readonly_fields = ("created_at", "pickup_token")  # NEW
    fields = (
        ("user", "service_day"),
        ("status", "delivery_status"),
        ("created_at", "pickup_token"),  # NEW: read-only no form
        ("delivered_at", "delivered_by"),
    )
    save_on_top = True

    # Helpers for columns
    @admin.display(boolean=True, description="Bloq.")
    def user_blocked(self, obj: Order) -> bool:
        return bool(getattr(obj.user, "is_blocked", False))

    @admin.display(description="Faltas seguidas")
    def user_no_show_streak(self, obj: Order) -> int:
        return int(getattr(obj.user, "no_show_streak", 0))

    # Actions: use services so streak + autoblock + audit are consistent
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

    # ---- Permission hardening: staff = read-only; superuser = full control ----
    def has_view_permission(self, request, obj=None):
        # Admin site already requires is_staff to access; allow staff to view list/detail
        return request.user.is_superuser or request.user.is_staff

    def has_add_permission(self, request):
        # Only superusers can create orders via Admin (“Pedidos”)
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        # Only superusers can edit orders in Admin
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        # Only superusers can delete orders in Admin
        return request.user.is_superuser

    def get_actions(self, request):
        # Hide mutating actions for non-superusers
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            return {}
        return actions

    # Optimize queries
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user", "delivered_by").prefetch_related("lines__item")


# Optional: separate admin for items — apply same superuser-only edit rule
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


# ─────────────────────────────────────────────────────────────────────────────
# Listagem (date picker + CSV export) — staff & admin can access
# ─────────────────────────────────────────────────────────────────────────────

# 1) Proxy model = separate Admin menu entry
class OrdersExport(Order):
    class Meta:
        proxy = True
        verbose_name = "Listagem"
        verbose_name_plural = "Listagem"


def _weekday_bit(d):  # Mon=0.Sun=6 -> 1<<weekday
    return 1 << d.weekday()


def _default_service_mask():
    # Mon–Fri by default if not set (0b11111)
    return getattr(settings, "DEFAULT_LUNCH_DAYS_MASK", 0b11111)


def _is_service_weekday(date_obj):
    return bool(_default_service_mask() & _weekday_bit(date_obj))


def _is_closed(date_obj):
    if DiaSemAtendimento is None:
        return False
    # Exact date
    if DiaSemAtendimento.objects.filter(data=date_obj).exists():
        return True
    # Annual repeats (same month/day)
    return DiaSemAtendimento.objects.filter(
        repete_anualmente=True, data__month=date_obj.month, data__day=date_obj.day
    ).exists()


def _next_eligible_service_day_global(now=None):
    """Midnight cutoff: always start from 'tomorrow', then skip non-service weekdays and closures."""
    tz_now = timezone.localtime(now or timezone.now())
    date_iter = timezone.localdate(tz_now) + timedelta(days=1)
    for _ in range(31):  # sane bound
        if _is_service_weekday(date_iter) and not _is_closed(date_iter):
            return date_iter
        date_iter += timedelta(days=1)
    return date_iter  # fallback, should not happen


def _nome_usuario(u):
    # Try common attributes; fall back to __str__
    full = None
    if hasattr(u, "get_full_name"):
        full = u.get_full_name()
    if not full:
        parts = filter(None, [getattr(u, "first_name", ""), getattr(u, "last_name", "")])
        full = " ".join(parts).strip()
    return full or str(u)


def _turma_usuario(u):
    # Best-effort extraction; adjust if your model has a known field.
    for attr in ("turma", "classroom", "class_name", "serie", "grade"):
        val = getattr(u, attr, None)
        if val:
            return str(val)
    return ""


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        y, m, d = map(int, value.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def _stream_csv_for(day: date, request):
    qs = (
        Order.objects.filter(service_day=day)
        .exclude(status__in=getattr(Order, "CANCELED_STATUSES", ("canceled",)))
        .select_related("user")
        .prefetch_related("lines__item")
    )

    # Compute totals per item (sum of line qty); fallback to "Prato do dia" × 1 if order has no lines
    totals = Counter()
    order_rows = []

    for order in qs:
        nome = _nome_usuario(order.user)
        turma = _turma_usuario(order.user)
        lines = list(order.lines.all())
        if not lines:
            # Fallback: 1x Prato do dia
            item_name = "Prato do dia"
            totals[item_name] += 1
            order_rows.append((turma or "", nome or "", item_name, 1))
        else:
            for line in lines:
                item_name = getattr(line.item, "name", str(line.item))
                qty = int(getattr(line, "qty", 0) or 0)
                totals[item_name] += qty
                order_rows.append((turma or "", nome or "", item_name, qty))

    # Build CSV
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="hango_pedidos_{day:%Y-%m-%d}.csv"'
    writer = csv.writer(resp, lineterminator="\n")

    # Header (human-friendly Portuguese)
    writer.writerow(["seção", "data", "nome", "turma", "item", "quantidade"])

    # Totals first (sort by item A→Z)
    for item_name in sorted(totals):
        writer.writerow(["TOTAL", day.strftime("%d/%m/%Y"), "", "", item_name, totals[item_name]])

    # Orders (one row per line item), sorted by turma then name then item
    for turma, nome, item_name, qty in sorted(order_rows, key=lambda r: (r[0], r[1], r[2])):
        writer.writerow(["PEDIDO", day.strftime("%d/%m/%Y"), nome, turma, item_name, qty])

    return resp


@admin.register(OrdersExport)
class OrdersExportAdmin(admin.ModelAdmin):
    """
    A dedicated Admin entry with a date picker; staff & admin can export CSV for any day.
    """
    change_list_template = "admin/orders_export_changelist.html"

    # Visibility & permissions
    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Date comes from ?data=YYYY-MM-DD (default = next eligible day)
        chosen = _parse_date(request.GET.get("data"))
        if not chosen:
            chosen = _next_eligible_service_day_global()

        # If ?export=1, stream CSV immediately
        if request.GET.get("export") == "1":
            return _stream_csv_for(chosen, request)

        context = {
            **self.admin_site.each_context(request),
            "title": "Listagem de pedidos",
            "target_day": chosen,
            "target_day_str": chosen.strftime("%Y-%m-%d"),
            "target_day_human": chosen.strftime("%d/%m/%Y"),
        }
        return TemplateResponse(request, self.change_list_template, context)
