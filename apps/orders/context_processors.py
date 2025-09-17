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
