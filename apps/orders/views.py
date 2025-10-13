# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from datetime import date as date_cls

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction, IntegrityError
from django.http import HttpRequest, HttpResponse
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
# Weekend placement gate
# ---------------------------------------------------------------------

def _orders_paused_today(user=None, now=None) -> bool:
    """
    Returns True if placing orders should be refused today.
    Policy: block order *placement* on Saturday (5) and Sunday (6).
    Staff bypass is allowed (set to block staff too if desired).
    """
    n = timezone.localtime(now or timezone.now())
    wk = n.weekday()  # Monday=0 ... Sunday=6
    if wk in (5, 6):
        # Allow staff to bypass. Flip to `return True` if you want staff blocked too.
        if user is not None and getattr(user, "is_staff", False):
            return False
        return True
    return False

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
                price = float(payload.get("price", 0.0))
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
                item = Item.objects.filter(pk=int(key)).first()
                if item:
                    name = getattr(item, "name", name)
            except Exception:
                pass
            price = 0.0

        if qty <= 0:
            continue

        lines.append(CartLine(key=str(key), name=name, price=price, qty=qty))

    return lines


def _cart_totals(lines: List[CartLine]) -> Tuple[int, float]:
    total_qty = sum(l.qty for l in lines)
    total_price = sum(l.subtotal for l in lines)
    return total_qty, total_price


# ---------------------------------------------------------------------
# Category helpers (for "one per category" rule)
# ---------------------------------------------------------------------

def _category_key(item: Item | None) -> str | None:
    """Return a stable key for the item's category (slug preferred)."""
    if not item or not getattr(item, "category_id", None):
        return None
    try:
        slug = getattr(item.category, "slug", None)
        return slug or f"cat:{item.category_id}"
    except Exception:
        return f"cat:{item.category_id}"


def _category_name(item: Item | None) -> str:
    """Human label for messages (“Almoço”, “Bebidas”, …)."""
    try:
        name = getattr(item.category, "name", None)
        if not name and hasattr(item.category, "__str__"):
            name = str(item.category)
        return str(name) if name else "categoria"
    except Exception:
        return "categoria"


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
    Add one unit of an item; enforce one-per-item and one-per-category in the cart.
    Quantities are always capped at 1.
    """
    cart = _get_session_cart(request)
    key = str(pk)

    # Load the item + its category for validation
    try:
        item = Item.objects.select_related("category").get(pk=int(pk))
    except Item.DoesNotExist:
        messages.error(request, "Item não encontrado.")
        return redirect("orders:cart")

    # Block items without a category (prevents bypassing category limits)
    cat_key = _category_key(item)
    if cat_key is None:
        messages.error(request, "Este item precisa estar em uma categoria antes de ser pedido.")
        return redirect("orders:cart")

    # 1) Disallow >1 of the same item
    current = cart.get(key, 0)
    current_qty = int(current.get("qty", current) if isinstance(current, dict) else current or 0)
    if current_qty >= 1:
        messages.error(request, f"Você pode escolher apenas 1 unidade de {item.name}.")
        return redirect("orders:cart")

    # 2) Disallow a second item from the same category already in the cart
    existing_ids: List[int] = []
    for k, payload in (cart or {}).items():
        try:
            q = int(payload.get("qty", payload) if isinstance(payload, dict) else payload or 0)
        except Exception:
            q = 0
        if q > 0:
            try:
                existing_ids.append(int(k))
            except Exception:
                pass

    if existing_ids:
        for it in Item.objects.filter(pk__in=existing_ids).select_related("category"):
            if _category_key(it) == cat_key:
                messages.warning(
                    request,
                    f"Você pode escolher apenas 1 item da categoria {_category_name(item)} por dia."
                )
                return redirect("orders:cart")

    # Passed validation → cap at 1
    cart[key] = 1
    _save_session_cart(request, cart)
    messages.success(request, "Adicionado ao carrinho.")
    return redirect("orders:cart")


@login_required
@require_http_methods(["POST"])
def remove(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove an item (sets qty to 0)."""
    cart = _get_session_cart(request)
    key = str(pk)

    if key in cart:
        cart.pop(key, None)
        _save_session_cart(request, cart)
        messages.info(request, "Removido do carrinho.")

    return redirect("orders:cart")


# ---------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
@login_required
def checkout(request: HttpRequest) -> HttpResponse:
    # Weekend guard: refuse placing orders on Sat/Sun for students.
    if _orders_paused_today(request.user):
        messages.error(request, "Pedidos ficam suspensos aos sábados e domingos. Tente novamente na segunda-feira.")
        return redirect("orders:cart")

    if request.method == "GET":
        cart = _get_session_cart(request)
        lines = _cart_lines(cart)
        total_qty, total_price = _cart_totals(lines)
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

    # === Per-item and per-category validation (server-side) ===
    from collections import Counter

    # Disallow any line with qty > 1
    for l in lines:
        if int(l.qty or 0) > 1:
            messages.warning(request, "Você pode escolher apenas 1 unidade de cada item.")
            return redirect("orders:cart")

    # Aggregate by category; each category can appear at most once (total qty <= 1)
    counts = Counter()
    cat_names: Dict[str, str] = {}

    # Preload items to avoid N+1
    id_map = {int(l.key): l for l in lines if str(l.key).isdigit()}
    items = Item.objects.filter(pk__in=id_map.keys()).select_related("category")

    for it in items:
        k = _category_key(it)
        if k is None:
            messages.error(request, f"O item {it.name} não possui categoria configurada.")
            return redirect("orders:cart")
        cat_names[k] = _category_name(it)
        counts[k] += int(id_map[int(it.pk)].qty or 0)

    # Any category with total > 1 is a violation
    for k, total in counts.items():
        if total > 1:
            messages.warning(request, f"Você pode escolher apenas 1 item da categoria {cat_names.get(k, 'categoria')} por dia.")
            return redirect("orders:cart")

    # Compute the service day (amanhã elegível) and enforce 1 por dia
    service_day = next_eligible_service_day(request.user)
    try:
        ensure_student_daily_limit(request.user, service_day, OrderModel=Order)
    except ValidationError as e:
        messages.warning(request, e.messages[0] if getattr(e, "messages", None) else "Você já possui um pedido para este dia.")
        return redirect("orders:cart")

    with transaction.atomic():
        try:
            order = Order.objects.create(user=request.user, service_day=service_day)

            for l in lines:
                try:
                    item_obj = Item.objects.get(pk=int(l.key))
                except (Item.DoesNotExist, ValueError):
                    item_obj = None
                OrderItem.objects.create(order=order, item=item_obj, qty=min(int(l.qty or 0), 1))

        except IntegrityError:
            # Race condition against the unique constraint (user, service_day)
            messages.warning(request, "Você já possui um pedido para este dia.")
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
    """View de supervisão: lista do dia, clique para marcar entregue/não entregue."""
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
    """Legacy manual status toggler (kept for compatibility)."""
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
      - delivered   → marca retirado e reseta streak
      - undelivered → marca no-show e atualiza streak
    """
    order = get_object_or_404(Order, pk=order_id)

    if state == "delivered":
        mark_picked_up(order, by=request.user)
        msg = "Marcado como entregue."
    elif state == "undelivered":
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
    """
    Resolve class/turma for a user. Falls back to StudentClass membership.
    """
    # direct attributes on User
    for attr in ("turma", "classroom", "class_name", "serie", "grade", "room",
                 "student_class", "current_class", "school_class", "classgroup", "studentclass"):
        val = getattr(u, attr, None)
        if val:
            return str(val)

    # profile-like containers
    for container in (getattr(u, "profile", None), getattr(u, "student", None), getattr(u, "aluno", None)):
        if container is not None:
            for attr in ("turma", "classroom", "class_name", "serie", "grade",
                         "primary_turma", "primary_class"):
                val = getattr(container, attr, None)
                if val:
                    if hasattr(val, "name"):
                        try:
                            return str(val.name)
                        except Exception:
                            pass
                    return str(val)

    # Classes app membership
    try:
        from apps.classes.models import StudentClass  # lazy import
        qs = StudentClass.objects.filter(members=u)
        try:
            qs = qs.filter(is_active=True)
        except Exception:
            pass
        classes = list(qs)
        if classes:
            import datetime as _dt
            def sort_key(c):
                y = getattr(c, "year", None) or getattr(c, "academic_year", None) or 0
                try: y = int(y or 0)
                except Exception: y = 0
                ca = getattr(c, "created_at", None)
                try:
                    ca = (ca or _dt.datetime.min.replace(tzinfo=None))
                    ca = ca.replace(tzinfo=None) if hasattr(ca, "tzinfo") else ca
                except Exception:
                    ca = _dt.datetime.min
                nm = getattr(c, "name", "") or ""
                return (y, ca, nm)
            classes.sort(key=sort_key, reverse=True)
            best = classes[0]
            name = getattr(best, "name", None)
            return str(name or best)
    except Exception:
        pass

    # Django groups fallback
    try:
        groups = getattr(u, "groups", None)
        if groups is not None and hasattr(groups, "all"):
            g = groups.all().first()
            if g:
                return getattr(g, "name", str(g))
    except Exception:
        pass

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
# Staff printable barcode sheet
# ---------------------------------------------------------------------

@login_required
@permission_required("orders.can_view_orders", raise_exception=True)
@require_http_methods(["GET"])
def barcodes_print(request: HttpRequest) -> HttpResponse:
    day_param = request.GET.get("day") or request.GET.get("data")
    day = _parse_day_param(day_param) or timezone.localdate()

    orders = list(
        Order.objects.filter(service_day=day)
        .exclude(status__in=getattr(Order, "CANCELED_STATUSES", ("canceled",)))
        .select_related("user")
        .prefetch_related("lines__item")
        .order_by("user__first_name", "user__last_name")
    )

    for o in orders:
        try:
            o.user_turma = _turma_usuario(o.user)
        except Exception:
            o.user_turma = ""

    return render(request, "orders/barcodes_print.html", {"orders": orders, "day": day})


# ---------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------

@login_required
@permission_required("orders.can_view_orders", raise_exception=True)
@require_http_methods(["GET"])
def export_orders_csv(request: HttpRequest) -> HttpResponse:
    day = _parse_day_param(request.GET.get("day")) or timezone.localdate()

    from collections import Counter
    import csv

    canceled_statuses = getattr(
        Order, "CANCELED_STATUSES",
        getattr(Order, "CANCELLED_STATUSES", ("canceled",))
    )

    qs = (
        Order.objects.filter(service_day=day)
        .exclude(**{"status__in": canceled_statuses})
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
    """Student's own order history with basic status flags."""
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
# Scan page (barcode/token → mark delivered)
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
                        "message": f"Pedido é de {dstr}.",
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
