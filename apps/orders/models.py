from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Order(models.Model):
    STATUS = [
        ("pending", _("Pending")),
        ("paid", _("Paid")),
        ("preparing", _("Preparing")),
        ("ready", _("Ready")),
        ("picked_up", _("Picked up")),
        ("canceled", _("Canceled")),
    ]

    DELIVERY_STATUS = [
        ("pending", _("Pending")),
        ("delivered", _("Delivered")),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    delivery_status = models.CharField(
        max_length=12, choices=DELIVERY_STATUS, default="pending"
    )
    service_day = models.DateField(default=timezone.localdate)
    pickup_slot = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivered_orders",
    )

    def __str__(self):
        return f"Order {self.pk} by {self.user}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("menu.Item", on_delete=models.PROTECT)
    qty = models.PositiveIntegerField()

    class Meta:
        unique_together = ("order", "item")
