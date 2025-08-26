from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView  # ← add this

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.menu.urls')),
    path('orders/', include('apps.orders.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('about/', TemplateView.as_view(template_name='about.html'), name='about'),  # ← new
]
