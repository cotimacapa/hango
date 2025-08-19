from django.urls import path
from . import views
app_name='menu'
urlpatterns=[path('', views.menu_list, name='list'), path('item/<int:pk>/add/', views.add_to_cart, name='add_to_cart')]
