from django.urls import path
from . import views

app_name = 'menu'

urlpatterns = [
    path('', views.splash, name='splash'),                 # /  -> splash
    path('menu/', views.menu_list, name='list'),           # /menu/ -> menu (login required)
    path('item/<int:pk>/add/', views.add_to_cart, name='add_to_cart'),
]
