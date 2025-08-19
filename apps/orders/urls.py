from django.urls import path
from . import views
app_name='orders'
urlpatterns=[path('cart/',views.view_cart,name='cart'), path('cart/add/<int:pk>/',views.add,name='add'), path('cart/remove/<int:pk>/',views.remove,name='remove'), path('checkout/',views.checkout,name='checkout'), path('success/<int:order_id>/',views.success,name='success')]
