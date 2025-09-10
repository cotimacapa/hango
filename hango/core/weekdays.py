# core/weekdays.py
from datetime import date

# Bit positions: Mon=1, Tue=2, Wed=4, Thu=8, Fri=16, Sat=32, Sun=64
WEEKDAY_BITS = [1, 2, 4, 8, 16, 32, 64]
MON_FRI_MASK = sum(WEEKDAY_BITS[:5])  # 31

WEEKDAY_LABELS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

def weekday_bit_for(d: date) -> int:
    """Return bit for Python weekday() where Monday=0..Sunday=6."""
    return WEEKDAY_BITS[d.weekday()]

def mask_from_bools(bools7):
    """bools7: iterable of 7 booleans [Mon..Sun] -> int mask."""
    mask = 0
    for i, on in enumerate(bools7):
        if on:
            mask |= WEEKDAY_BITS[i]
    return mask

def bools_from_mask(mask: int):
    """Return list[7] of booleans for Mon..Sun."""
    return [(mask & WEEKDAY_BITS[i]) != 0 for i in range(7)]

def human_days(mask: int, labels=WEEKDAY_LABELS_PT) -> str:
    """e.g., 31 -> 'Seg, Ter, Qua, Qui, Sex' or '—' if none."""
    if not mask:
        return "—"
    parts = [labels[i] for i in range(7) if (mask & WEEKDAY_BITS[i])]
    return ", ".join(parts)
