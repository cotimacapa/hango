from django.contrib import admin
from django.urls import path, include
urlpatterns=[path('admin/', admin.site.urls), path('', include('apps.menu.urls')), path('orders/', include('apps.orders.urls'))]
