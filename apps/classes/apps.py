from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class ClassesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.classes"
    verbose_name = _("Classes")  # This becomes the section title on the admin home
