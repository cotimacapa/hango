from collections import Counter
import datetime

from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required       # NEW
from django.views.decorators.http import require_POST                         # NEW
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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


@login_required
def view_cart(request):
    lines = _cart_items(request)
    return render(request, 'orders/cart.html', {"lines": lines})


@login_required
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
    messages.success(request, _("Item added to cart."))
    return redirect('orders:cart')


@login_required
def remove(request, pk):
    cart = request.session.get('cart', {})
    if str(pk) in cart:
        del cart[str(pk)]
        request.session['cart'] = cart
        messages.info(request, _("Item removed."))
    return redirect('orders:cart')


@login_required
def checkout(request):
    lines = _cart_items(request)
    if not lines:
        messages.warning(request, _("Your cart is empty."))
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
            msg_lines.append(_("%(cat)s: limit %(quota)s/day (you already have %(already)s today, trying to add %(adding)s).") % {"cat": slug.replace("-", " ").title(), "quota": quota, "already": already, "adding": adding})

@login_required
def success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'orders/success.html', {'order': order})

@staff_member_required
def kitchen_board(request):
    """
    Today's orders with quick status actions, sorted by status then time.
    Template can auto-refresh periodically.
    """
    start = timezone.localdate()
    start_dt = timezone.make_aware(datetime.datetime.combine(start, datetime.time.min))
    end_dt = timezone.make_aware(datetime.datetime.combine(start, datetime.time.max))

    orders_qs = (
        Order.objects
        .filter(created_at__range=(start_dt, end_dt))
        .exclude(status='canceled')
        .select_related('user')
        .prefetch_related('lines__item')
        .order_by('created_at')
    )

    status_rank = {'pending': 0, 'paid': 1, 'preparing': 2, 'ready': 3, 'picked_up': 4}
    orders = sorted(orders_qs, key=lambda o: (status_rank.get(o.status, 99), o.created_at))

    actions_map = {
        'pending':   [('preparing', 'Start'), ('ready', 'Ready'), ('canceled', 'Cancel')],
        'paid':      [('preparing', 'Start'), ('ready', 'Ready'), ('canceled', 'Cancel')],
        'preparing': [('ready', 'Ready'), ('canceled', 'Cancel')],
        'ready':     [('picked_up', 'Picked up'), ('canceled', 'Cancel')],
        'picked_up': [],
        'canceled':  [],
    }

    rows = [{'order': o, 'actions': actions_map.get(o.status, [])} for o in orders]

    # Provide both 'rows' (preferred) and 'orders'/'ACTIONS' for compatibility
    return render(request, 'orders/kitchen.html', {
        'rows': rows,
        'orders': orders,
        'ACTIONS': actions_map,
        'now': timezone.now(),
    })


@staff_member_required
@require_POST
def update_status(request, order_id, new_status):
    """Validate state transition and save."""
    new_status = (new_status or '').lower()
    valid = dict(Order.STATUS)
    order = get_object_or_404(Order, id=order_id)

    if new_status not in valid:
        messages.error(request, "Invalid status.")
        return redirect('orders:kitchen')

    allowed = {
        'pending':   {'preparing', 'ready', 'canceled', 'paid'},
        'paid':      {'preparing', 'ready', 'canceled'},
        'preparing': {'ready', 'canceled'},
        'ready':     {'picked_up', 'canceled'},
        'picked_up': set(),
        'canceled':  set(),
    }.get(order.status, set())

    if new_status not in allowed:
        messages.warning(request, f"Cannot change {order.get_status_display()} → {valid[new_status]}.")
        return redirect('orders:kitchen')

    order.status = new_status
    order.save(update_fields=['status'])
    messages.success(request, f"Order #{order.id} → {order.get_status_display()}")
    return redirect('orders:kitchen')
