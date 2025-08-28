from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf.urls.i18n import set_language


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.menu.urls')),
    path('orders/', include('apps.orders.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('about/', TemplateView.as_view(template_name='about.html'), name='about'),
    path("i18n/set-language/", set_language, name="set_language"),
]
