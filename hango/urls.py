# hango/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.views.i18n import set_language  # language switch endpoint

urlpatterns = [
    path('admin/', admin.site.urls),

    # App routes
    path('', include('apps.menu.urls')),
    path('orders/', include('apps.orders.urls')),

    # Auth (login/logout/password reset, etc.)
    # Provides /accounts/login/ using your templates/registration/login.html
    path('accounts/', include('django.contrib.auth.urls')),

    # Static pages
    path('about/', TemplateView.as_view(template_name='about.html'), name='about'),

    # Language switch endpoint
    path('i18n/set-language/', set_language, name='set_language'),
]
