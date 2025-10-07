# apps/reports/apps.py
from django.apps import AppConfig

class ReportsConfig(AppConfig):
    name = "apps.reports"
    label = "reports"           # ensures its own admin section
    verbose_name = "Relatórios (Em teste)" # admin sidebar section title
