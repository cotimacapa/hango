from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.contrib.auth.decorators import user_passes_test

from apps.menu.models import Item
from .models import Order, OrderItem


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
    Build CartLine[] from session cart in either shape:
      A) {"<id>": {"name": str, "price": float, "qty": int}}
      B) {"<id>": <qty int>}
    Falls back to Item lookup for name/price if payload is int.
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
    messages.success(request, _("Added to cart."))
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
        messages.info(request, _("Removed from cart."))

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
            # Silent redirect; the cart page already communicates empty state.
            return redirect("orders:cart")
        return render(
            request,
            "orders/checkout.html",
            {"lines": lines, "total_qty": total_qty, "total_price": total_price},
        )

    if not lines:
        # Avoid extra message spam; just go back.
        return redirect("orders:cart")

    with transaction.atomic():
        # Model defaults (status, delivery_status, service_day) handle required fields.
        order = Order.objects.create(user=request.user)

        for l in lines:
            try:
                item_obj = Item.objects.get(pk=int(l.key))
            except (Item.DoesNotExist, ValueError):
                item_obj = None
            OrderItem.objects.create(order=order, item=item_obj, qty=l.qty)

    _clear_session_cart(request)
    messages.success(request, _("Order placed successfully."))
    return redirect("orders:success", order_id=order.pk)


@require_http_methods(["GET"])
@login_required
def success(request: HttpRequest, order_id: int) -> HttpResponse:
    return render(request, "orders/success.html", {"order_id": order_id})


# ---------------------------------------------------------------------
# Kitchen / status
# ---------------------------------------------------------------------

@require_http_methods(["GET"])
@login_required
def kitchen_board(request: HttpRequest) -> HttpResponse:
    try:
        return render(request, "orders/kitchen.html", {
            "orders": Order.objects.filter(service_day=timezone.localdate()).order_by("-created_at")[:200],
        })
    except Exception:
        return HttpResponse("Kitchen board", content_type="text/plain")
    

@require_http_methods(["POST", "GET"])
@login_required
def update_status(request: HttpRequest, order_id: int, new_status: str) -> HttpResponse:
    order = get_object_or_404(Order, pk=order_id)
    order.status = new_status
    order.save(update_fields=["status"])
    messages.success(request, _("Order status updated."))
    return redirect("orders:kitchen")

@require_http_methods(["POST"])
@login_required
@user_passes_test(lambda u: u.is_staff)
def set_delivery_status(request: HttpRequest, order_id: int, state: str) -> HttpResponse:
    """
    Green ✓ sets delivery_status='delivered' and stamps delivered_at/by.
    Red ✕ sets delivery_status='pending' and clears delivered_at/by.
    Staff only.
    """
    order = get_object_or_404(Order, pk=order_id)

    if state == "delivered":
        order.delivery_status = "delivered"
        order.delivered_at = timezone.now()
        order.delivered_by = request.user
        msg = _("Marked as delivered.")
    else:
        order.delivery_status = "pending"
        order.delivered_at = None
        order.delivered_by = None
        msg = _("Marked as not delivered.")

    order.save(update_fields=["delivery_status", "delivered_at", "delivered_by"])
    messages.success(request, msg)
    return redirect("orders:kitchen")

