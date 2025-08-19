from django.shortcuts import render, get_object_or_404, redirect
from .models import Item

def menu_list(request):
    items = Item.objects.filter(is_active=True).order_by('name')
    return render(request, 'menu/menu_list.html', {'items': items})

def add_to_cart(request, pk):
    get_object_or_404(Item, pk=pk, is_active=True)
    cart = request.session.get('cart', {})
    cart[str(pk)] = cart.get(str(pk), 0) + 1
    request.session['cart'] = cart
    return redirect('menu:list')
