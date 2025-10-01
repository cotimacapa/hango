from django.db import migrations

def create_studentpickup_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    ct, _ = ContentType.objects.get_or_create(app_label="orders", model="studentpickupstat")

    wanted = [
        ("add_studentpickupstat",    "Pode adicionar estatística de retirada"),
        ("change_studentpickupstat", "Pode alterar estatística de retirada"),
        ("delete_studentpickupstat", "Pode excluir estatística de retirada"),
        ("view_studentpickupstat",   "Pode visualizar estatística de retirada"),
    ]
    for codename, name in wanted:
        Permission.objects.update_or_create(
            codename=codename, content_type=ct, defaults={"name": name}
        )

def drop_studentpickup_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    try:
        ct = ContentType.objects.get(app_label="orders", model="studentpickupstat")
    except ContentType.DoesNotExist:
        return
    Permission.objects.filter(
        content_type=ct,
        codename__in=[
            "add_studentpickupstat",
            "change_studentpickupstat",
            "delete_studentpickupstat",
            "view_studentpickupstat",
        ],
    ).delete()

class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0009_delete_ordersexport"),
    ]
    operations = [
        migrations.RunPython(create_studentpickup_permissions, drop_studentpickup_permissions),
    ]
