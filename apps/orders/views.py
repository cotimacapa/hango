from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.menu.models import Item
from .models import Order, OrderItem

# NEW: import the order services (step 2.2)
from apps.orders.services import mark_no_show, mark_picked_up  # NEW


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


def _save_session_cart(request: HttpRequest, cart: Dict[str, Dict[str, Any]]) -> None:
    request.session["cart"] = cart
    request.session.modified = True


def _cart_lines(request: HttpRequest) -> List[CartLine]:
    """
    Constrói CartLine[] a partir do carrinho em sessão em dois formatos:
      A) {"<id>": {"name": str, "price": float, "qty": int}}
      B) {"<id>": <qty int>}
    Se o payload for int, busca nome/preço em Item.
    """
    raw = _get_session_cart(request)
    lines: List[CartLine] = []

    for key, payload in raw.items():
        name = str(key)
        price = 0.0
        qty = 0

        if isinstance(payload, dict):
            name = str(payload.get("name", name))
            try:
                price = float(payload.get("price", 0.0))
            except Exception:
                price = 0.0
            try:
                qty = int(payload.get("qty", 0))
            except Exception:
                qty = 0
        else:
            try:
                qty = int(payload)
            except Exception:
                qty = 0
            try:
                item = Item.objects.filter(pk=int(key)).first()
                if item:
                    name = getattr(item, "name", name)
                    price = float(getattr(item, "price", 0.0))
            except Exception:
                pass

        if qty <= 0:
            continue

        lines.append(CartLine(key=str(key), name=name, price=price, qty=qty))

    return lines


def _cart_totals(lines: List[CartLine]) -> Tuple[int, float]:
    total_qty = sum(l.qty for l in lines)
    total_price = sum(l.subtotal for l in lines)
    return total_qty, float(total_price)


def _clear_session_cart(request: HttpRequest) -> None:
    if "cart" in request.session:
        request.session["cart"] = {}
        request.session.modified = True


# ---------------------------------------------------------------------
# Cart views
# ---------------------------------------------------------------------

@require_http_methods(["GET"])
@login_required
def view_cart(request: HttpRequest) -> HttpResponse:
    lines = _cart_lines(request)
    return render(request, "orders/cart.html", {"lines": lines})


@require_http_methods(["POST", "GET"])
@login_required
def add(request: HttpRequest, pk: int) -> HttpResponse:
    _ = Item.objects.filter(pk=pk).first()
    cart = _get_session_cart(request)
    key = str(pk)
    entry = cart.get(key)

    if isinstance(entry, dict):
        entry["qty"] = int(entry.get("qty", 0)) + 1
        cart[key] = entry
    elif entry is not None:
        cart[key] = int(entry) + 1
    else:
        cart[key] = 1

    _save_session_cart(request, cart)
    messages.success(request, "Adicionado ao carrinho.")
    return redirect("orders:cart")


@require_http_methods(["POST", "GET"])
@login_required
def remove(request: HttpRequest, pk: int) -> HttpResponse:
    cart = _get_session_cart(request)
    key = str(pk)

    if key in cart:
        entry = cart[key]
        if isinstance(entry, dict):
            new_qty = int(entry.get("qty", 0)) - 1
            if new_qty <= 0:
                cart.pop(key, None)
            else:
                entry["qty"] = new_qty
                cart[key] = entry
        else:
            new_qty = int(entry) - 1
            if new_qty <= 0:
                cart.pop(key, None)
            else:
                cart[key] = new_qty

        _save_session_cart(request, cart)
        messages.info(request, "Removido do carrinho.")

    return redirect("orders:cart")


# ---------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
@login_required
def checkout(request: HttpRequest) -> HttpResponse:
    lines = _cart_lines(request)
    total_qty, total_price = _cart_totals(lines)

    if request.method == "GET":
        if not lines:
            # Redireciona silenciosamente; a página do carrinho já informa vazio.
            return redirect("orders:cart")
        return render(
            request,
            "orders/checkout.html",
            {"lines": lines, "total_qty": total_qty, "total_price": total_price},
        )

    # NEW: Enforce blocking at order time
    if getattr(request.user, "is_blocked", False):  # NEW
        messages.error(request, "Seu usuário está bloqueado para fazer pedidos. Procure a equipe.")  # NEW
        return redirect("orders:cart")  # NEW

    if not lines:
        # Evita mensagens extras; apenas volta.
        return redirect("orders:cart")

    with transaction.atomic():
        # Defaults do modelo lidam com campos obrigatórios.
        order = Order.objects.create(user=request.user)

        for l in lines:
            try:
                item_obj = Item.objects.get(pk=int(l.key))
            except (Item.DoesNotExist, ValueError):
                item_obj = None
            OrderItem.objects.create(order=order, item=item_obj, qty=l.qty)

    _clear_session_cart(request)
    messages.success(request, "Pedido realizado com sucesso.")
    return redirect("orders:success", order_id=order.pk)


@require_http_methods(["GET"])
@login_required
def success(request: HttpRequest, order_id: int) -> HttpResponse:
    return render(request, "orders/success.html", {"order_id": order_id})


# ---------------------------------------------------------------------
# Kitchen / status
# ---------------------------------------------------------------------

@require_http_methods(["GET"])
@staff_member_required
def kitchen_board(request: HttpRequest) -> HttpResponse:
    """
    Mostra apenas pedidos pendentes do dia.
    """
    try:
        orders = (
            Order.objects.filter(
                service_day=timezone.localdate(),
                delivery_status="pending",
            )
            .select_related("user")
            .prefetch_related("lines__item")
            .order_by("-created_at")[:200]
        )
        return render(request, "orders/kitchen.html", {"orders": orders})
    except Exception:
        return HttpResponse("Cozinha", content_type="text/plain")


@require_http_methods(["POST"])
@staff_member_required
def update_status(request: HttpRequest, order_id: int, new_status: str) -> HttpResponse:
    """
    Manipulador legado multi-estado (mantido por ora; restrito a staff).
    Prefira set_delivery_status no fluxo novo.
    """
    order = get_object_or_404(Order, pk=order_id)
    order.status = new_status
    order.save(update_fields=["status"])
    messages.success(request, "Status do pedido atualizado.")
    return redirect("orders:kitchen")


@require_http_methods(["POST"])
@staff_member_required
def set_delivery_status(request: HttpRequest, order_id: int, state: str) -> HttpResponse:
    """
    Define o status de entrega via dois botões:
      - state == "delivered"   → marca retirado e reseta streak
      - state == "undelivered" → marca no-show e atualiza streak (auto-bloqueia em 3)
    Depois redireciona para a Cozinha (a linha some por não estar mais pendente).
    """
    order = get_object_or_404(Order, pk=order_id)

    if state == "delivered":
        # UPDATED: use the helper (also sets delivered_at/by and resets streak)
        mark_picked_up(order, by=request.user)  # NEW
        msg = "Marcado como entregue."
    elif state == "undelivered":
        # UPDATED: use the helper (sets no_show/undelivered, increments streak, may auto-block)
        mark_no_show(order)  # NEW
        msg = "Marcado como não entregue."
    else:
        messages.error(request, "Status inválido.")
        return redirect("orders:kitchen")

    messages.success(request, msg)
    return redirect("orders:kitchen")


# ---------------------------------------------------------------------
# Pedidos (Orders) daily list
# ---------------------------------------------------------------------

@staff_member_required
@require_http_methods(["GET"])
def orders_list(request: HttpRequest) -> HttpResponse:
    """
    Página de Pedidos: mostra todos os pedidos *não pendentes* em um dia.
    Padrão: hoje. Selecione outra data via ?date=YYYY-MM-DD.
    """
    qdate = request.GET.get("date")
    if qdate:
        try:
            selected_date = datetime.strptime(qdate, "%Y-%m-%d").date()
        except ValueError:
            selected_date = timezone.localdate()
    else:
        selected_date = timezone.localdate()

    orders = (
        Order.objects.filter(service_day=selected_date)
        .exclude(delivery_status="pending")
        .select_related("user")
        .prefetch_related("lines__item")
        .order_by("-created_at")
    )

    context = {
        "selected_date": selected_date,
        "orders": orders,
        "page_title": "Pedidos",
    }
    return render(request, "orders/list.html", context)
