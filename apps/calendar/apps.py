from django.apps import AppConfig

class CalendarConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.calendar"
    verbose_name = "Calendário e Horas"

    def ready(self):
        from . import signals  # noqa: F401