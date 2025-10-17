from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import Order

# Default threshold for auto-blocking on consecutive no-shows.
AUTO_BLOCK_THRESHOLD_DEFAULT: int = getattr(settings, "HANGO_AUTO_BLOCK_THRESHOLD", 3)


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
    Marca o pedido como retirado e zera a sequência de faltas do usuário.
    """
    prev = order.status
    order = order.mark_picked_up(by=by)
    u = order.user
    return MarkResult(
        order_id=order.pk,
        user_id=u.pk,
        prev_status=prev,
        new_status=order.status,
        no_show_streak=getattr(u, "no_show_streak", 0) or 0,
        blocked=bool(getattr(u, "is_blocked", False)),
        block_source=getattr(u, "block_source", None),
    )


@transaction.atomic
def mark_no_show(order: Order, *, auto_block_threshold: Optional[int] = None) -> MarkResult:
    """
    Marca o pedido como não comparecido, incrementa a sequência e bloqueia se atingir o limite.
    Corrigido: salva o incremento ANTES de chamar block() para não perder a atualização.
    """
    threshold = AUTO_BLOCK_THRESHOLD_DEFAULT if auto_block_threshold is None else int(auto_block_threshold)
    prev = order.status

    # Atualiza o pedido
    if order.status != "no_show":
        order.status = "no_show"
        order.delivery_status = "undelivered"
        order.save(update_fields=["status", "delivery_status"])

    u = order.user
    u.no_show_streak = (u.no_show_streak or 0) + 1
    u.last_no_show_at = timezone.localdate()

    # 1) Persist first, so increment is never lost
    u.save(update_fields=["no_show_streak", "last_no_show_at"])

    # 2) Then handle blocking
    if (u.no_show_streak >= threshold) and not getattr(u, "is_blocked", False):
        u.block(source="auto", by=None, reason=f"{threshold} faltas consecutivas")

    return MarkResult(
        order_id=order.pk,
        user_id=u.pk,
        prev_status=prev,
        new_status=order.status,
        no_show_streak=u.no_show_streak,
        blocked=bool(getattr(u, "is_blocked", False)),
        block_source=getattr(u, "block_source", None),
    )
