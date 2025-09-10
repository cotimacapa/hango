# apps/orders/services/no_show.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from django.utils import timezone
from django.db import transaction

from apps.orders.models import Order  # adjust path if your app label differs

AUTO_BLOCK_THRESHOLD_DEFAULT = 3  # 3 faltas consecutivas


@dataclass
class MarkResult:
    order_id: int
    user_id: int
    prev_status: str
    new_status: str
    no_show_streak: int
    blocked: bool
    block_source: Optional[str]


@transaction.atomic
def mark_picked_up(order: Order, *, by=None) -> MarkResult:
    """
    Marca o pedido como 'picked_up', registra entrega e zera a sequência de faltas do usuário.
    """
    prev = order.status
    if order.status != "picked_up":
        order.status = "picked_up"
        order.delivery_status = "delivered"
        order.delivered_at = timezone.now()
        if by is not None and getattr(by, "is_staff", False):
            order.delivered_by = by
        order.save(update_fields=["status", "delivery_status", "delivered_at", "delivered_by"])

    u = order.user
    if u.no_show_streak != 0 or not u.last_pickup_at:
        u.no_show_streak = 0
        u.last_pickup_at = timezone.localdate()
        u.save(update_fields=["no_show_streak", "last_pickup_at"])

    return MarkResult(
        order_id=order.pk,
        user_id=u.pk,
        prev_status=prev,
        new_status=order.status,
        no_show_streak=u.no_show_streak,
        blocked=u.is_blocked,
        block_source=u.block_source or None,
    )


@transaction.atomic
def mark_no_show(
    order: Order,
    *,
    auto_block_threshold: int = AUTO_BLOCK_THRESHOLD_DEFAULT,
) -> MarkResult:
    """
    Marca o pedido como 'no_show', incrementa a sequência de faltas e
    bloqueia automaticamente ao atingir 'auto_block_threshold' (padrão: 3).
    """
    prev = order.status
    if order.status != "no_show":
        order.status = "no_show"
        order.delivery_status = "undelivered"
        order.save(update_fields=["status", "delivery_status"])

    u = order.user
    u.no_show_streak = (u.no_show_streak or 0) + 1
    u.last_no_show_at = timezone.localdate()

    blocked_now = False
    if (u.no_show_streak >= auto_block_threshold) and not u.is_blocked:
        # usa os helpers do modelo User (gera BlockEvent)
        u.block(source="auto", by=None, reason=f"{auto_block_threshold} faltas consecutivas")
        blocked_now = True
    else:
        u.save(update_fields=["no_show_streak", "last_no_show_at"])

    return MarkResult(
        order_id=order.pk,
        user_id=u.pk,
        prev_status=prev,
        new_status=order.status,
        no_show_streak=u.no_show_streak,
        blocked=u.is_blocked,
        block_source=("auto" if blocked_now else (u.block_source or None)),
    )
