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


# ────────────────────────────────────────────────────────────────
# 🔧 NEW: Recalculate the true consecutive no-show streak
# ────────────────────────────────────────────────────────────────

def recalculate_no_show_streak(user):
    """
    Recompute the user's consecutive no-show streak by walking
    backward through their orders until a delivered one is found.
    """
    today = timezone.localdate()
    orders = (
        Order.objects.filter(user=user, service_day__lte=today)
        .exclude(status__in=("canceled",))
        .order_by("-service_day")
        .values_list("status", flat=True)
    )

    streak = 0
    for status in orders:
        if status in ("no_show", "undelivered"):
            streak += 1
        elif status == "delivered":
            break
    user.no_show_streak = streak
    user.last_no_show_at = timezone.localdate() if streak else None
    user.save(update_fields=["no_show_streak", "last_no_show_at"])
    return streak


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
    threshold = AUTO_BLOCK_THRESHOLD_DEFAULT if auto_block_threshold is None else int(auto_block_threshold)
    prev = order.status

    # Ensure order is marked correctly
    if order.status != "no_show":
        order.status = "no_show"
        order.delivery_status = "undelivered"
        order.save(update_fields=["status", "delivery_status"])

    u = order.user

    # Increment and save immediately
    u.no_show_streak = (u.no_show_streak or 0) + 1
    u.last_no_show_at = timezone.localdate()
    u.save(update_fields=["no_show_streak", "last_no_show_at"])

    # 🩺 Refresh inside the same transaction to guarantee latest values
    u.refresh_from_db(fields=["no_show_streak", "is_blocked"])

    # Now safely evaluate the blocking condition
    if u.no_show_streak >= threshold and not u.is_blocked:
        # Ensure the updated streak is committed before blocking
        transaction.on_commit(lambda: u.refresh_from_db(fields=["no_show_streak"]))
        u.block(source="auto", by=None, reason=f"{threshold} faltas consecutivas")

    return MarkResult(
        order_id=order.pk,
        user_id=u.pk,
        prev_status=prev,
        new_status=order.status,
        no_show_streak=u.no_show_streak,
        blocked=u.is_blocked,
        block_source=getattr(u, "block_source", None),
    )
