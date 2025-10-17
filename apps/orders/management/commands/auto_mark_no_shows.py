from datetime import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order

# Cutoff 13:30 local (America/Belem)
CUTOFF_HOUR = 13
CUTOFF_MINUTE = 30


class Command(BaseCommand):
    help = (
        "Às 13:30 (ou depois), marca como 'no_show' todo pedido PENDENTE "
        "com service_day <= hoje. Não toca pedidos futuros."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignora o horário limite (apenas para testes manuais).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria alterado sem salvar mudanças.",
        )

    def handle(self, *args, **options):
        now_local = timezone.localtime()
        cutoff_dt = timezone.make_aware(
            timezone.datetime.combine(
                timezone.localdate(),
                time(CUTOFF_HOUR, CUTOFF_MINUTE),
            ),
            timezone.get_current_timezone(),
        )

        # Only run after cutoff unless --force
        if not options["force"] and now_local < cutoff_dt:
            self.stdout.write(self.style.WARNING(
                f"Agora {now_local:%H:%M} < {cutoff_dt:%H:%M}. Nada a fazer (sem --force)."
            ))
            return

        today = timezone.localdate()

        # Eligible: pending/active orders for today or any past day (never future),
        # excluding already picked_up, already no_show, and canceled.
        qs = (
            Order.objects
            .select_for_update(skip_locked=True)
            .filter(service_day__lte=today)
            .exclude(status__in=("picked_up", "no_show") + Order.CANCELED_STATUSES)
        )

        total = qs.count()
        if not total:
            self.stdout.write(self.style.NOTICE("Nenhum pedido elegível para marcar como no_show."))
            return

        updated = 0
        with transaction.atomic():
            for order in qs:
                if options["dry_run"]:
                    self.stdout.write(f"[DRY] #{order.id} — {order.user} seria marcado como no_show.")
                else:
                    order.mark_no_show(save_user=True)
                    updated += 1

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Simulação concluída — nada salvo."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{updated} pedido(s) marcados como no_show."))
