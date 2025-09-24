from django.db import migrations
import secrets

def _ean13_check_digit(d12: str) -> str:
    s = 0
    for i, ch in enumerate(d12):
        n = int(ch)
        s += (3 * n) if ((i + 1) % 2 == 0) else n
    return str((10 - (s % 10)) % 10)

def _generate_ean13() -> str:
    d12 = "".join(str(secrets.randbelow(10)) for _ in range(12))
    return d12 + _ean13_check_digit(d12)

def backfill_tokens(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    existing = set(Order.objects.exclude(pickup_token__isnull=True).values_list("pickup_token", flat=True))
    batch = []
    for order in Order.objects.filter(pickup_token__isnull=True).only("id"):
        for _ in range(8):
            tok = _generate_ean13()
            if tok not in existing:
                existing.add(tok)
                batch.append((order.id, tok))
                break
    for oid, tok in batch:
        Order.objects.filter(id=oid).update(pickup_token=tok)

class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_order_pickup_token"),  # replace with the auto-generated schema migration
    ]
    operations = [
        migrations.RunPython(backfill_tokens, migrations.RunPython.noop),
    ]
