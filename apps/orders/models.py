from django.conf import settings
from django.db import models
from django.utils import timezone

# NEW: threshold for auto-block
AUTO_BLOCK_THRESHOLD = 3  # 3 faltas consecutivas


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
    service_day = models.DateField("Dia de atendimento", default=timezone.localdate)
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

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"

    def __str__(self):
        return f"Pedido {self.pk} de {self.user}"

    # ──────────────────────────────────────────────────────────────────────
    # NEW: Helpers para integrar com a lógica de faltas / bloqueio
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
        on_delete=models.CASCADE,
        related_name="lines",
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
