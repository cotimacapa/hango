from collections import Counter
import datetime
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
    items = Item.objects.filter(id__in=item_ids).select_related("category")
    lines = []
    for it in items:
        qty = cart.get(str(it.id), 0)
        lines.append({"item": it, "qty": qty})
    return lines

def _user_counts_today(user):
    """Counts items by category for all non-canceled orders created today."""
    counts = Counter()
    if not user.is_authenticated:
        return counts
    start = timezone.localdate()
    start_dt = timezone.make_aware(datetime.datetime.combine(start, datetime.time.min))
    end_dt = timezone.make_aware(datetime.datetime.combine(start, datetime.time.max))
    qs = OrderItem.objects.select_related("item__category").filter(
        order__user=user,
        order__created_at__range=(start_dt, end_dt)
    ).exclude(order__status="canceled")
    for oi in qs:
        cat = getattr(getattr(oi.item, "category", None), "slug", None)
        if cat:
            counts[cat] += oi.qty
    return counts

def _cart_counts(cart):
    """Counts items by category in the current cart."""
    counts = Counter()
    item_ids = [int(k) for k in cart.keys()]
    for it in Item.objects.filter(id__in=item_ids).select_related("category"):
        if it.category:
            counts[it.category.slug] += cart.get(str(it.id), 0)
    return counts

def view_cart(request):
    lines = _cart_items(request)
    return render(request, 'orders/cart.html', {"lines": lines})

def add(request, pk):
    item = get_object_or_404(Item, pk=pk, is_active=True)
    cart = request.session.get('cart', {})
    # If we know the user and the item has a quota, check before adding
    if request.user.is_authenticated and item.category and item.category.daily_quota:
        current = _user_counts_today(request.user) + _cart_counts(cart)
        used = current[item.category.slug]
        if used + 1 > item.category.daily_quota:
            messages.warning(
                request,
                f"Daily limit reached for {item.category.name} "
                f"({item.category.daily_quota} per day)."
            )
            return redirect('orders:cart')

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

    # Final server-side enforcement (covers guests who add before logging in)
    cart = request.session.get('cart', {})
    have = _user_counts_today(request.user)
    need = _cart_counts(cart)

    # Look up quotas for categories present in cart
    from apps.menu.models import Category  # local import to avoid circulars
    quotas = {c.slug: c.daily_quota for c in Category.objects.all() if c.daily_quota}

    violations = []
    for slug, qty in need.items():
        quota = quotas.get(slug)
        if quota and (have.get(slug, 0) + qty) > quota:
            violations.append((slug, quota, have.get(slug, 0), qty))

    if violations:
        msg_lines = []
        for slug, quota, already, adding in violations:
            msg_lines.append(f"{slug.replace('-', ' ').title()}: limit {quota}/day "
                             f"(you already have {already} today, trying to add {adding}).")
        messages.error(request, "Daily limits exceeded:\n" + "\n".join(msg_lines))
        return redirect('orders:cart')

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
