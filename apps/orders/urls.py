from django.urls import path
from . import views

app_name = "orders"

urlpatterns = [
    path('cart/', views.view_cart, name='cart'),
    path('cart/add/<int:pk>/', views.add, name='add'),
    path('cart/remove/<int:pk>/', views.remove, name='remove'),
    path('checkout/', views.checkout, name='checkout'),
    path('success/<int:order_id>/', views.success, name='success'),

    path('kitchen/', views.kitchen_board, name='kitchen'),
    path('status/<int:order_id>/<str:new_status>/', views.update_status, name='update_status'),
    path('deliver/<int:order_id>/<str:state>/', views.set_delivery_status, name='deliver'),

    path('scan/', views.scan, name='scan'),

    # Pedidos list + CSV export
    path('list/', views.orders_list, name='list'),
    path('export/', views.export_orders_csv, name='export_csv'),

    path('history/', views.order_history, name='history'),
]
