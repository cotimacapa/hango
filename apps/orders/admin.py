# apps/orders/admin.py
from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from .models import Order, OrderItem
from apps.orders.services import mark_no_show, mark_picked_up


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
    search_fields = ("user__cpf", "user__first_name", "user__last_name")
    readonly_fields = ("created_at",)
    fields = (
        ("user", "service_day"),
        ("status", "delivery_status"),
        ("created_at",),
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

    # Optimize queries
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user", "delivered_by").prefetch_related("lines__item")


# Optional: separate admin for items (usually unnecessary because of inline)
@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "item", "qty")
    list_select_related = ("order", "item")
    search_fields = ("order__id", "item__name", "order__user__cpf")
    list_filter = (("order__service_day", admin.DateFieldListFilter),)
    autocomplete_fields = ("order", "item")
