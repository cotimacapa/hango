# lunch/eligibility.py
from datetime import date
from django.utils import timezone
from core.weekdays import weekday_bit_for

def effective_lunch_days_mask(user) -> int:
    """
    Returns the allowed weekday mask for this user.
    Assumes user has .profile and .turma relations per your project.
    """
    if getattr(user, "is_staff", False):
        return 0
    profile = getattr(user, "profile", None)
    if profile and profile.lunch_days_override_enabled:
        return profile.lunch_days_override_mask or 0
    turma = getattr(user, "turma", None)
    return getattr(turma, "days_mask", 0) or 0

def is_lunch_day_for_user(user, target_date: date | None = None) -> bool:
    if target_date is None:
        # Use local date in America/Belem (your project tz)
        target_date = timezone.localdate()
    mask = effective_lunch_days_mask(user)
    return (mask & weekday_bit_for(target_date)) != 0
