# apps/orders/context_processors.py
from django.utils import timezone

def cart_count(request):
    cart=request.session.get('cart',{})
    return {'cart_count': sum(cart.values())}

def greeting(request):
    """Portuguese greeting based on local time."""
    hour = timezone.localtime().hour
    if 5 <= hour < 12:
        text = "Bom dia"
    elif 12 <= hour < 18:
        text = "Boa tarde"
    else:
        text = "Boa noite"
    return {"greeting_pt": text}

def cart_count(request):
    """
    Total quantity of items in the session cart.

    Accepts both legacy shapes:
      - {"42": 3}
      - {"42": {"qty": 3, ...}}
    """
    cart = request.session.get("cart") or {}
    total = 0
    for v in cart.values():
        if isinstance(v, dict):
            try:
                total += int(v.get("qty", 0))
            except Exception:
                continue
        else:
            try:
                total += int(v)
            except Exception:
                continue
    return {"cart_count": total}
