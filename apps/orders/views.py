from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from apps.menu.models import Item
from .models import Order, OrderItem
from .forms import CheckoutForm

def _cart_items(request):
    cart = request.session.get('cart', {})
    item_ids = [int(k) for k in cart.keys()]
    items = Item.objects.filter(id__in=item_ids)
    lines = []
    for it in items:
        qty = cart.get(str(it.id), 0)
        lines.append({"item": it, "qty": qty})
    return lines

def view_cart(request):
    lines = _cart_items(request)
    return render(request, 'orders/cart.html', {"lines": lines})

def add(request, pk):
    get_object_or_404(Item, pk=pk, is_active=True)
    cart = request.session.get('cart', {})
    cart[str(pk)] = cart.get(str(pk), 0) + 1
    request.session['cart'] = cart
    messages.success(request, "Item added to cart.")
    return redirect('orders:cart')

def remove(request, pk):
    cart = request.session.get('cart', {})
    if str(pk) in cart:
        del cart[str(pk)]
        request.session['cart'] = cart
        messages.info(request, "Item removed.")
    return redirect('orders:cart')

@login_required
def checkout(request):
    lines = _cart_items(request)
    if not lines:
        messages.warning(request, "Your cart is empty.")
        return redirect('menu:list')

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            order = Order.objects.create(
                user=request.user,
                status='pending',
                pickup_slot=form.cleaned_data.get('pickup_slot'),
                notes=form.cleaned_data.get('notes', ''),
                created_at=timezone.now()
            )
            for l in lines:
                OrderItem.objects.create(order=order, item=l['item'], qty=l['qty'])
            request.session['cart'] = {}
            return redirect('orders:success', order_id=order.id)
    else:
        form = CheckoutForm()

    return render(request, 'orders/checkout.html', {'form': form, 'lines': lines})

@login_required
def success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'orders/success.html', {'order': order})
