from django.conf import settings
from django.db import models
from django.utils import timezone


class Order(models.Model):
    # Status geral do pedido (se você ainda usa essas fases)
    STATUS = [
        ("pending", "Pendente"),
        ("paid", "Pago"),
        ("preparing", "Preparando"),
        ("ready", "Pronto"),
        ("picked_up", "Retirado"),
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
    notes = models.TextField("Observações", blank=True)
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

    def __str__(self):
        return f"Pedido {self.pk} de {self.user}"


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
