from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from datetime import date as date_cls

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction, IntegrityError
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden  # UPDATED
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError

from apps.menu.models import Item
from .models import Order, OrderItem

# Order services (status helpers + scheduling & daily limit)
from apps.orders.services import (
    mark_no_show,
    mark_picked_up,
    next_eligible_service_day,
    ensure_student_daily_limit,
)


# ---------------------------------------------------------------------
# Session-cart helpers
# ---------------------------------------------------------------------

@dataclass
class CartLine:
    key: str
    name: str
    price: float
    qty: int

    @property
    def subtotal(self) -> float:
        return float(self.price) * int(self.qty)


def _get_session_cart(request: HttpRequest) -> Dict[str, Dict[str, Any]]:
    data = request.session.get("cart")
    if isinstance(data, dict):
        return data
    return {}


def _save_session_cart(request: HttpRequest, data: Dict[str, Dict[str, Any]]) -> None:
    request.session["cart"] = data
    request.session.modified = True


def _clear_session_cart(request: HttpRequest) -> None:
    if "cart" in request.session:
        del request.session["cart"]
        request.session.modified = True


def _cart_lines(cart: Dict[str, Any]) -> List[CartLine]:
    """
    Expand raw session cart into CartLine objects (best-effort).
    Accepts both {'id': qty} and {'id': {'name':..., 'price':..., 'qty':...}} shapes.
    NOTE: Hango is free; we do NOT read Item.price from the DB.
    """
    lines: List[CartLine] = []
    for key, payload in (cart or {}).items():
        name = f"Item {key}"
        price = 0.0
        qty = 0

        if isinstance(payload, dict):
            name = payload.get("name", name)
            try:
                price = float(payload.get("price", 0.0))  # may be absent; default 0.0
            except Exception:
                price = 0.0
            try:
                qty = int(payload.get("qty", 0))
            except Exception:
                qty = 0
        else:
            # Legacy shape: cart[key] = qty (no name/price)
            try:
                qty = int(payload)
            except Exception:
                qty = 0
            try:
                # Only fetch name; NEVER read a price from DB.
                item = Item.objects.filter(pk=int(key)).first()
                if item:
                    name = getattr(item, "name", name)
            except Exception:
                pass
            price = 0.0  # explicit

        if qty <= 0:
            continue

        lines.append(CartLine(key=str(key), name=name, price=price, qty=qty))

    return lines


def _cart_totals(lines: List[CartLine]) -> Tuple[int, float]:
    total_qty = sum(l.qty for l in lines)
    total_price = sum(l.subtotal for l in lines)
    return total_qty, total_price


# ---------------------------------------------------------------------
# Cart & checkout views
# ---------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def view_cart(request: HttpRequest) -> HttpResponse:
    cart = _get_session_cart(request)
    lines = _cart_lines(cart)
    total_qty, total_price = _cart_totals(lines)

    context = {
        "lines": lines,
        "total_qty": total_qty,
        "total_price": total_price,
    }
    return render(request, "orders/cart.html", context)


@login_required
@require_http_methods(["POST"])
def add(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Store quantities as plain ints in the session cart (legacy-compatible).
    """
    cart = _get_session_cart(request)
    key = str(pk)

    current = cart.get(key, 0)
    if isinstance(current, dict):
        qty = int(current.get("qty", 0)) + 1
    else:
        qty = int(current) + 1 if current else 1

    cart[key] = qty  # keep it as an int
    _save_session_cart(request, cart)
    messages.success(request, "Adicionado ao carrinho.")
    return redirect("orders:cart")


@login_required
@require_http_methods(["POST"])
def remove(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Decrement quantities and keep the session value as an int.
    """
    cart = _get_session_cart(request)
    key = str(pk)

    if key in cart:
        current = cart[key]
        qty = int(current.get("qty", 0)) if isinstance(current, dict) else int(current)
        qty -= 1
        if qty <= 0:
            cart.pop(key, None)
        else:
            cart[key] = qty  # keep it as an int
        _save_session_cart(request, cart)
        messages.info(request, "Removido do carrinho.")

    return redirect("orders:cart")


# ---------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
@login_required
def checkout(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        cart = _get_session_cart(request)
        lines = _cart_lines(cart)
        total_qty, total_price = _cart_totals(lines)

        # Compute the service day (amanhã elegível)
        service_day = next_eligible_service_day(request.user)

        context = {
            "lines": lines,
            "total_qty": total_qty,
            "total_price": total_price,
            "service_day": service_day,
        }
        return render(request, "orders/checkout.html", context)

    # POST
    cart = _get_session_cart(request)
    lines = _cart_lines(cart)
    if not lines:
        messages.error(request, "Seu carrinho está vazio.")
        return redirect("orders:cart")

    # Compute the service day (amanhã elegível) and enforce 1 por dia
    service_day = next_eligible_service_day(request.user)
    try:
        ensure_student_daily_limit(request.user, service_day, OrderModel=Order)
    except ValidationError as e:
        messages.error(request, e.messages[0] if getattr(e, "messages", None) else "Você já possui um pedido para este dia.")
        return redirect("orders:cart")

    with transaction.atomic():
        try:
            order = Order.objects.create(user=request.user, service_day=service_day)

            for l in lines:
                try:
                    item_obj = Item.objects.get(pk=int(l.key))
                except (Item.DoesNotExist, ValueError):
                    item_obj = None
                OrderItem.objects.create(order=order, item=item_obj, qty=l.qty)

        except IntegrityError:
            # Race condition against the unique constraint (user, service_day)
            messages.error(request, "Você já possui um pedido para este dia.")
            return redirect("orders:cart")

    _clear_session_cart(request)
    messages.success(request, "Pedido realizado com sucesso.")
    return redirect("orders:success", order_id=order.pk)


@require_http_methods(["GET"])
@login_required
def success(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    return render(request, "orders/success.html", {"order": order})


# ---------------------------------------------------------------------
# Kitchen board (current manual flow)
# ---------------------------------------------------------------------

@login_required
@permission_required("orders.can_view_kitchen", raise_exception=True)
@require_http_methods(["GET"])
def kitchen_board(request: HttpRequest) -> HttpResponse:
    """
    View de supervisão: lista do dia, clique para marcar entregue/não entregue.
    """
    today = timezone.localdate()
    orders = (
        Order.objects.filter(service_day=today, delivery_status="pending")
        .select_related("user")
        .prefetch_related("lines__item")
        .order_by("created_at")
    )
    return render(request, "orders/kitchen.html", {"orders": orders, "today": today})


@require_http_methods(["POST"])
@login_required
@permission_required("orders.can_view_kitchen", raise_exception=True)
def update_status(request: HttpRequest, order_id: int, new_status: str) -> HttpResponse:
    """
    Legacy manual status toggler (kept for compatibility).
    Prefira set_delivery_status no fluxo novo.
    """
    order = get_object_or_404(Order, pk=order_id)
    order.status = new_status
    order.save(update_fields=["status"])
    messages.success(request, "Status do pedido atualizado.")
    return redirect("orders:kitchen")


@require_http_methods(["POST"])
@login_required
@permission_required("orders.can_manage_delivery", raise_exception=True)
def set_delivery_status(request: HttpRequest, order_id: int, state: str) -> HttpResponse:
    """
    Define o status de entrega via dois botões:
      - state == "delivered"   → marca retirado e reseta streak
      - state == "undelivered" → marca no-show e atualiza streak (auto-bloqueia em 3)
    Depois redireciona para a Cozinha (a linha some por não estar mais pendente).
    """
    order = get_object_or_404(Order, pk=order_id)

    if state == "delivered":
        # Use the helper (also sets delivered_at/by and resets streak)
        mark_picked_up(order, by=request.user)
        msg = "Marcado como entregue."
    elif state == "undelivered":
        # Use the helper (sets no_show/undelivered, increments streak, may auto-block)
        mark_no_show(order)
        msg = "Marcado como não entregue."
    else:
        messages.error(request, "Estado inválido.")
        return redirect("orders:kitchen")

    messages.success(request, msg)
    return redirect("orders:kitchen")


# ---------------------------------------------------------------------
# Helpers for Pedidos & Export
# ---------------------------------------------------------------------

def _parse_day_param(value: str | None):
    if not value:
        return None
    try:
        y, m, d = map(int, value.split("-"))
        return date_cls(y, m, d)
    except Exception:
        return None

def _nome_usuario(u):
    full = getattr(u, "get_full_name", lambda: "")() or " ".join(
        [getattr(u, "first_name", ""), getattr(u, "last_name", "")]
    ).strip()
    return full or str(u)

def _turma_usuario(u):
    for attr in ("turma", "classroom", "class_name", "serie", "grade"):
        val = getattr(u, attr, None)
        if val:
            return str(val)
    return ""


# ---------------------------------------------------------------------
# Staff daily orders list (now with date param)
# ---------------------------------------------------------------------

@login_required
@permission_required("orders.can_view_orders", raise_exception=True)
@require_http_methods(["GET"])
def orders_list(request: HttpRequest) -> HttpResponse:
    # support ?day=YYYY-MM-DD (alias ?data= too)
    day_param = request.GET.get("day") or request.GET.get("data")
    day = _parse_day_param(day_param) or timezone.localdate()

    orders = (
        Order.objects.filter(service_day=day)
        .exclude(status__in=getattr(Order, "CANCELED_STATUSES", ("canceled",)))
        .select_related("user")
        .prefetch_related("lines__item")
        .order_by("user__first_name", "user__last_name")
    )
    return render(request, "orders/orders_list.html", {"orders": orders, "day": day})


# ---------------------------------------------------------------------
# Export CSV (moved from Admin)
# ---------------------------------------------------------------------

@login_required
@permission_required("orders.can_view_orders", raise_exception=True)
@require_http_methods(["GET"])
def export_orders_csv(request: HttpRequest) -> HttpResponse:
    day = _parse_day_param(request.GET.get("day")) or timezone.localdate()

    from collections import Counter
    import csv

    qs = (
        Order.objects.filter(service_day=day)
        .exclude(status__in=getattr(Order, "CANCELED_STATUSES", ("canceled",)))
        .select_related("user")
        .prefetch_related("lines__item")
    )

    # Totals per item + per-order rows
    totals = Counter()
    order_rows = []
    for order in qs:
        nome = _nome_usuario(order.user)
        turma = _turma_usuario(order.user)
        lines = list(order.lines.all())
        if not lines:
            item_name = "Prato do dia"
            totals[item_name] += 1
            order_rows.append((turma or "", nome or "", item_name, 1))
        else:
            for line in lines:
                item_name = getattr(line.item, "name", str(line.item))
                qty = int(getattr(line, "qty", 0) or 0)
                totals[item_name] += qty
                order_rows.append((turma or "", nome or "", item_name, qty))

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


# ---------------------------------------------------------------------
# Student history
# ---------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def order_history(request: HttpRequest) -> HttpResponse:
    """
    Student's own order history with basic status flags.
    """
    orders = (
        Order.objects.filter(user=request.user)
        .select_related("user")
        .prefetch_related("lines__item")
        .order_by("-created_at")[:200]
    )
    context = {
        "orders": orders,
        "is_blocked": bool(getattr(request.user, "is_blocked", False)),
        "no_show_streak": int(getattr(request.user, "no_show_streak", 0) or 0),
    }
    return render(request, "orders/history.html", context)


# ---------------------------------------------------------------------
# NEW: Scan page (barcode/token → mark delivered)
# ---------------------------------------------------------------------

def _ean13_check_digit(n12: str) -> str:
    s = 0
    for i, ch in enumerate(n12):
        d = int(ch)
        s += (3 * d) if ((i + 1) % 2 == 0) else d
    return str((10 - (s % 10)) % 10)

def _ean13_is_valid(code: str) -> bool:
    if not code or len(code) != 13 or not code.isdigit():
        return False
    return _ean13_check_digit(code[:12]) == code[-1]

@login_required
@permission_required("orders.can_manage_delivery", raise_exception=True)
@require_http_methods(["GET", "POST"])
def scan(request: HttpRequest) -> HttpResponse:
    """
    Counter-fast lane: one focused input. Scanner types 13 digits + Enter.
    Server validates, constrains to today's orders, and marks delivered.
    """
    today = timezone.localdate()
    context: Dict[str, Any] = {"today": today, "result": None}

    if request.method == "GET":
        return render(request, "orders/scan.html", context)

    # POST
    raw = (request.POST.get("token") or "").strip()
    token = "".join(ch for ch in raw if ch.isdigit())

    if not _ean13_is_valid(token):
        context.update({"result": "error", "error": "Token inválido (formato EAN-13)."})
        return render(request, "orders/scan.html", context)

    # Try to deliver today's order with this token
    with transaction.atomic():
        order = (
            Order.objects.select_for_update()
            .filter(pickup_token=token, service_day=today)
            .select_related("user")
            .first()
        )

        if order is None:
            # Investigate: wrong day or nonexistent?
            any_order = Order.objects.filter(pickup_token=token).select_related("user").first()
            if any_order:
                if any_order.delivered_at:
                    ts = timezone.localtime(any_order.delivered_at).strftime("%H:%M")
                    context.update({
                        "result": "already",
                        "order": any_order,
                        "message": f"Já entregue às {ts}.",
                    })
                else:
                    dstr = any_order.service_day.strftime("%d/%m/%Y")
                    context.update({
                        "result": "wrongday",
                        "order": any_order,
                        "message": f"Pedido não é de hoje (é de {dstr}).",
                    })
            else:
                context.update({"result": "notfound", "error": "Token não encontrado."})
            return render(request, "orders/scan.html", context)

        # If it's already delivered, be idempotent
        if order.delivered_at:
            ts = timezone.localtime(order.delivered_at).strftime("%H:%M")
            context.update({"result": "already", "order": order, "message": f"Já entregue às {ts}."})
            return render(request, "orders/scan.html", context)

        # Mark delivered using your service helper (resets streak, sets delivered_by/at)
        mark_picked_up(order, by=request.user)

    context.update({"result": "ok", "order": order})
    return render(request, "orders/scan.html", context)
