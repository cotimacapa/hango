from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.views.i18n import set_language
from apps.accounts import views as accounts_views   # import our router

urlpatterns = [
    path('admin/', admin.site.urls),

    # App routes
    path('', include('apps.menu.urls')),
    path('orders/', include('apps.orders.urls')),

    # Auth (login/logout/password reset, etc.)
    path('accounts/', include('django.contrib.auth.urls')),

    # Static pages
    path('about/', TemplateView.as_view(template_name='about.html'), name='about'),

    # Language switch endpoint
    path('i18n/set-language/', set_language, name='set_language'),

    # Post-login redirect router
    path('post-login/', accounts_views.post_login_redirect, name='post_login_redirect'),
]
