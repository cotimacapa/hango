# apps/orders/models.py
from django.conf import settings
from django.db import models
from django.utils import timezone

import secrets

# NEW: threshold for auto-block
AUTO_BLOCK_THRESHOLD = 3  # 3 faltas consecutivas


def _ean13_check_digit(d12: str) -> str:
    """
    Calcula o dígito verificador EAN-13 para 12 dígitos.
    Pesos: posições ímpares=1, pares=3 (indexação 1..12 da esquerda p/ direita).
    """
    s = 0
    for i, ch in enumerate(d12):
        n = int(ch)
        s += (3 * n) if ((i + 1) % 2 == 0) else n
    return str((10 - (s % 10)) % 10)


def _generate_ean13() -> str:
    """Gera 12 dígitos aleatórios e anexa o DV EAN-13 (total = 13 dígitos)."""
    d12 = "".join(str(secrets.randbelow(10)) for _ in range(12))
    return d12 + _ean13_check_digit(d12)


class Order(models.Model):
    # Status geral do pedido (se você ainda usa essas fases)
    STATUS = [
        ("pending", "Pendente"),
        # ("paid", "Pago"),
        # ("preparing", "Preparando"),
        # ("ready", "Pronto"),
        ("picked_up", "Retirado"),
        ("no_show", "Não compareceu"),  # NEW
        ("canceled", "Cancelado"),
    ]

    # Status de entrega (fluxo da Cozinha/Pedidos)
    DELIVERY_STATUS = [
        ("pending", "Pendente"),
        ("delivered", "Entregue"),
        ("undelivered", "Não Entregue"),  # adicionado para casar com o fluxo atual
    ]

    # NEW: estados que NÃO contam para a regra "1 pedido por dia"
    CANCELED_STATUSES = ("canceled",)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Usuário",
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        "Status",
        max_length=12,
        choices=STATUS,
        default="pending",
    )
    delivery_status = models.CharField(
        "Status de entrega",
        max_length=12,
        choices=DELIVERY_STATUS,
        default="pending",
    )
    # IMPORTANTE: a aplicação deve preencher este campo com o "próximo dia elegível".
    # O default abaixo evita nulos em criações manuais, mas não substitui a regra.
    service_day = models.DateField("Dia de atendimento", default=timezone.localdate, db_index=True)
    pickup_slot = models.DateTimeField("Horário de retirada", null=True, blank=True)
    created_at = models.DateTimeField("Criado em", default=timezone.now)
    delivered_at = models.DateTimeField("Entregue em", null=True, blank=True)
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Entregue por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivered_orders",
    )

    # NEW: token opaco (somente dígitos), pronto para EAN-13 (13 chars)
    pickup_token = models.CharField(
        "Token de retirada",
        max_length=13,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        editable=False,
        help_text="Token opaco para retirada no balcão (EAN-13, sem PII).",
    )

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        permissions = [
            ("can_view_kitchen", "Can view kitchen board"),
            ("can_manage_delivery", "Can mark delivered / no-show"),
            ("can_view_orders", "Can view daily orders list"),
        ]
        # NEW: 1 pedido ativo por estudante por dia (o app libera em cancelamento)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "service_day"],
                name="one_order_per_student_per_service_day",
            )
        ]

    def __str__(self):
        return f"Pedido {self.pk} de {self.user}"

    # ──────────────────────────────────────────────────────────────────────
    # NEW: token lifecycle
    # ──────────────────────────────────────────────────────────────────────
    def ensure_pickup_token(self, *, force: bool = False) -> str:
        """
        Garante que o pedido possua um token EAN-13 exclusivo.
        Usa 12 dígitos aleatórios + DV; re-tenta em caso de colisão.
        """
        if self.pickup_token and not force:
            return self.pickup_token

        for _ in range(8):
            candidate = _generate_ean13()
            if not type(self).objects.filter(pickup_token=candidate).exists():
                self.pickup_token = candidate
                return candidate
        # Em casos extremamente improváveis
        raise RuntimeError("Falha ao alocar pickup_token após várias tentativas")

    def save(self, *args, **kwargs):
        # Atribui token apenas na criação (mantém tokens estáveis)
        if self.pk is None and not self.pickup_token:
            self.ensure_pickup_token()
        super().save(*args, **kwargs)

    # ──────────────────────────────────────────────────────────────────────
    # Helpers para integrar com a lógica de faltas / bloqueio
    # ──────────────────────────────────────────────────────────────────────
    def mark_picked_up(self, by=None, *, save_user=True):
        """
        Marca como retirado, registra entrega, e zera streak de faltas do usuário.
        """
        if self.status == "picked_up":
            return self
        self.status = "picked_up"
        self.delivery_status = "delivered"
        self.delivered_at = timezone.now()
        self.delivered_by = by if (by and getattr(by, "is_staff", False)) else self.delivered_by
        self.save(update_fields=["status", "delivery_status", "delivered_at", "delivered_by"])

        # reset da sequência de faltas
        if save_user:
            u = self.user
            if u.no_show_streak != 0 or not u.last_pickup_at:
                u.no_show_streak = 0
                u.last_pickup_at = timezone.localdate()
                u.save(update_fields=["no_show_streak", "last_pickup_at"])
        return self

    def mark_no_show(self, *, auto_block_threshold: int = AUTO_BLOCK_THRESHOLD, save_user=True):
        """
        Marca como 'não compareceu', incrementa streak e faz auto-bloqueio ao atingir o limite.
        """
        if self.status == "no_show":
            return self
        self.status = "no_show"
        self.delivery_status = "undelivered"
        self.save(update_fields=["status", "delivery_status"])

        if save_user:
            u = self.user
            u.no_show_streak = (u.no_show_streak or 0) + 1
            u.last_no_show_at = timezone.localdate()

            if (u.no_show_streak >= auto_block_threshold) and not u.is_blocked:
                # chama o helper do modelo User (registra BlockEvent)
                u.block(source="auto", by=None, reason=f"{auto_block_threshold} faltas consecutivas")
            else:
                u.save(update_fields=["no_show_streak", "last_no_show_at"])
        return self


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        verbose_name="Pedido",
        related_name="lines",
        on_delete=models.CASCADE,
    )
    item = models.ForeignKey(
        "menu.Item",
        verbose_name="Item",
        on_delete=models.PROTECT,
    )
    qty = models.PositiveIntegerField("Quantidade")

    class Meta:
        unique_together = ("order", "item")
        verbose_name = "Item do pedido"
        verbose_name_plural = "Itens do pedido"

    def __str__(self):
        return f"{self.qty}× {self.item}"
