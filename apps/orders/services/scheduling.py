# apps/orders/services/scheduling.py
from __future__ import annotations
from datetime import timedelta, date

from django.conf import settings
from django.utils import timezone
from apps.classes.models import ExtraLunchDay

from datetime import time as dtime
# “Dias sem atendimento” live in the calendar app
try:
    from apps.calendar.models import DiaSemAtendimento
except Exception:
    DiaSemAtendimento = None  # calendar app might not be installed in some envs


# ---------------------------------------------------------------------
# Bit helpers
# ---------------------------------------------------------------------

def _weekday_bit(d: date) -> int:
    """Mon=0 … Sun=6 → 1<<weekday bitmask."""
    return 1 << d.weekday()


def _coerce_int_mask(value, default=None):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


# Which attribute on the class/turma stores the integer mask?
def _candidate_mask_attrs():
    names = []
    cfg = getattr(settings, "LUNCH_CLASS_MASK_FIELD", None)
    if cfg:
        names.append(cfg)
    # common fallbacks
    names.extend([
        "lunch_days_mask",
        "lunch_days_override_mask",
        "delivery_days_mask",
        "weekdays_mask",
        "weekday_mask",
        "dias_semana_mask",
        "dias_de_almoco",
        "days_mask",
        "mask",
    ])
    seen, ordered = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            ordered.append(n)
    return tuple(ordered)


_MASK_ATTR_CANDIDATES = _candidate_mask_attrs()

# common boolean field names per weekday (Mon..Sun)
_BOOLEAN_DAY_FIELDS = [
    ("monday",   "segunda",  "seg"),
    ("tuesday",  "terca",    "ter"),
    ("wednesday","quarta",   "qua"),
    ("thursday", "quinta",   "qui"),
    ("friday",   "sexta",    "sex"),
    ("saturday", "sabado",   "sab"),
    ("sunday",   "domingo",  "dom"),
]


def _mask_from_booleans(obj) -> int | None:
    """
    Build a mask from boolean weekday fields if present.
    Mon=bit0 … Sun=bit6.
    """
    bits = 0
    found_any = False
    for idx, names in enumerate(_BOOLEAN_DAY_FIELDS):
        for nm in names:
            if hasattr(obj, nm):
                try:
                    if bool(getattr(obj, nm)):
                        bits |= (1 << idx)
                except Exception:
                    pass
                found_any = True
                break  # stop at first matching alias for this weekday
    return bits if found_any else None


def _mask_from_obj(obj) -> int | None:
    """Return an integer mask from a related object."""
    if not obj:
        return None

    # 1) direct integer field
    for attr in _MASK_ATTR_CANDIDATES:
        if hasattr(obj, attr):
            m = _coerce_int_mask(getattr(obj, attr), None)
            if m is not None:
                return m

    # 2) derive from booleans
    m = _mask_from_booleans(obj)
    if m is not None:
        return m

    return None


def _mask_from_related_any(user) -> int | None:
    """
    Scan ALL relations on the user and return the first mask we can find.
    For M2M, combine with OR.
    """
    try:
        fields = user._meta.get_fields()
    except Exception:
        return None

    # Forward relations first
    for f in fields:
        if not getattr(f, "is_relation", False):
            continue
        name = getattr(f, "name", None)
        if not name:
            continue
        try:
            rel = getattr(user, name)
        except Exception:
            continue

        if hasattr(rel, "__class__") and not hasattr(rel, "all"):
            m = _mask_from_obj(rel)
            if m is not None:
                return m
        else:
            try:
                qs = rel.all()
            except Exception:
                continue
            combined = 0
            found = False
            for obj in qs:
                m = _mask_from_obj(obj)
                if m is not None:
                    combined |= m
                    found = True
            if found:
                return combined

    # Reverse accessors (rare)
    for f in fields:
        if not getattr(f, "is_relation", False):
            continue
        if not getattr(f, "auto_created", False):
            continue
        name = getattr(f, "get_accessor_name", lambda: None)()
        if not name:
            continue
        try:
            rel = getattr(user, name)
        except Exception:
            continue
        try:
            qs = rel.all()
        except Exception:
            continue
        for obj in qs:
            m = _mask_from_obj(obj)
            if m is not None:
                return m

    return None


def _default_mask() -> int:
    return int(getattr(settings, "DEFAULT_LUNCH_DAYS_MASK", 0b11111))


def _user_lunch_mask(user) -> int:
    """
    Resolve weekday bitmask (Mon=0..Sun=6). Priority:
      1) Per-user override **only if enabled** (lunch_days_override_enabled)
      2) Relation in settings.LUNCH_CLASS_REL (FK or M2M)
      3) Explicit common relation names
      4) Any related object exposing a mask field / booleans
      5) Global default (Mon–Fri)
    """
    # 1) per-user override (guarded by enable flag)
    if getattr(user, "lunch_days_override_enabled", False):
        override = _coerce_int_mask(getattr(user, "lunch_days_override_mask", None), None)
        if override is not None:
            return override

    # 2) relation from settings
    rel_name = getattr(settings, "LUNCH_CLASS_REL", None)
    if rel_name:
        rel = getattr(user, rel_name, None)
        if rel is not None:
            if hasattr(rel, "__class__") and not hasattr(rel, "all"):  # FK/O2O
                m = _mask_from_obj(rel)
                if m is not None:
                    return m
            else:  # M2M
                try:
                    qs = rel.all()
                except Exception:
                    qs = []
                combined = 0
                found = False
                for obj in qs:
                    m = _mask_from_obj(obj)
                    if m is not None:
                        combined |= m
                        found = True
                if found:
                    return combined

    # 3) explicit common relation names as fallbacks
    for rel_name in ("turma", "classroom", "class_group", "classroom_group", "group", "turmas", "classrooms", "student_classes"):
        rel = getattr(user, rel_name, None)
        if rel is None:
            continue
        if hasattr(rel, "__class__") and not hasattr(rel, "all"):
            m = _mask_from_obj(rel)
            if m is not None:
                return m
        else:
            try:
                qs = rel.all()
            except Exception:
                qs = []
            combined = 0
            found = False
            for obj in qs:
                m = _mask_from_obj(obj)
                if m is not None:
                    combined |= m
                    found = True
            if found:
                return combined

    # 4) generic scan
    any_mask = _mask_from_related_any(user)
    if any_mask is not None:
        return any_mask

    # 5) default
    return _default_mask()


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def is_lunch_day_for_user(user, dia: date) -> bool:
    """
    Returns True if the user can order lunch for the given date.
    Includes both regular lunch days (mask) and temporary extra days.
    """
    try:
        # If this date is explicitly marked as an extra lunch day
        # for any of the user's classes, it's valid.
        if ExtraLunchDay.objects.filter(
            student_class__in=user.student_classes.all(),
            date=dia
        ).exists():
            return True
    except Exception:
        # Fallback if user has no student_classes relation
        pass

    # Default behavior: regular weekday mask check
    return bool(_user_lunch_mask(user) & _weekday_bit(dia))

def is_closed(dia: date) -> bool:
    if DiaSemAtendimento is None:
        return False
    if DiaSemAtendimento.objects.filter(data=dia).exists():
        return True
    return DiaSemAtendimento.objects.filter(
        repete_anualmente=True, data__month=dia.month, data__day=dia.day
    ).exists()


# import the setting reader
from apps.calendar.models import OrderCutoffSetting  # adjust path to your app

def next_eligible_service_day(user, now=None) -> date:
    """
    Configurable cutoff:
      - Before cutoff local time: base = today + 1
      - At/After cutoff:          base = today + 2
    Then skip non-service weekdays and closures.
    """
    tz_now = timezone.localtime(now or timezone.now())
    today = timezone.localdate(tz_now)

    cutoff = OrderCutoffSetting.get_cutoff_time(default_hour=15, default_minute=0)
    base_days = 1 if tz_now.time() < cutoff else 2

    dia = today + timedelta(days=base_days)

    for _ in range(31):
        if is_lunch_day_for_user(user, dia) and not is_closed(dia):
            return dia
        dia += timedelta(days=1)

    return today + timedelta(days=base_days)

# --- daily limit enforcement -------------------------------------------------
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def ensure_student_daily_limit(user, service_day, order_model=None, **kwargs):
    """
    Raise ValidationError if the student already has an order for the given
    service_day. Accepts either `order_model=` or legacy `OrderModel=`.
    """
    # Allow legacy kw name used by your view
    if order_model is None:
        order_model = kwargs.get("OrderModel")

    # Default to local Order model if not provided
    if order_model is None:
        from apps.orders.models import Order  # local import to avoid cycles
        order_model = Order

    # Correct field: service_day (not service_date)
    if order_model.objects.filter(user=user, service_day=service_day).exists():
        raise ValidationError(_("Você já possui um pedido para esse dia."))
