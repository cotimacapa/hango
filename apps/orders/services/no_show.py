# apps/orders/services/no_show.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.db import transaction

from ..models import Order


# Default threshold for auto-blocking on consecutive no-shows.
# Override in settings.py with: HANGO_AUTO_BLOCK_THRESHOLD = 3
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
    Mark as delivered/picked up, set delivered_at/by, and reset the user's no-show streak.
    Delegates to Order.mark_picked_up to keep business rules centralized.
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
    Mark as no-show/undelivered, increment the user's streak, and auto-block if threshold reached.
    Delegates to Order.mark_no_show.
    """
    threshold = AUTO_BLOCK_THRESHOLD_DEFAULT if auto_block_threshold is None else int(auto_block_threshold)
    prev = order.status
    order = order.mark_no_show(auto_block_threshold=threshold)
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
