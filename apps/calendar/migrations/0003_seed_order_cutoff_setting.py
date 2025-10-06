from django.db import migrations
from datetime import time

def seed_cutoff(apps, schema_editor):
    Setting = apps.get_model('calendar', 'OrderCutoffSetting')  # app label, model name
    if not Setting.objects.exists():
        Setting.objects.create(cutoff_time=time(15, 0))

def unseed_cutoff(apps, schema_editor):
    Setting = apps.get_model('calendar', 'OrderCutoffSetting')
    Setting.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('calendar', '0002_ordercutoffsetting'),  # keep the auto-added dependency
    ]

    operations = [
        migrations.RunPython(seed_cutoff, unseed_cutoff)
    ]
