from django.conf import settings
from django.db import models
from django.utils import timezone
class Order(models.Model):
    STATUS=[('pending','Pending'),('paid','Paid'),('preparing','Preparing'),('ready','Ready'),('picked_up','Picked up'),('canceled','Canceled')]
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    status=models.CharField(max_length=12,choices=STATUS,default='pending')
    pickup_slot=models.DateTimeField(null=True,blank=True)
    notes=models.TextField(blank=True)
    subtotal_cents=models.PositiveIntegerField(default=0)
    total_cents=models.PositiveIntegerField(default=0)
    created_at=models.DateTimeField(default=timezone.now)
    def __str__(self): return f'Order {self.pk} by {self.user}'
class OrderItem(models.Model):
    order=models.ForeignKey(Order,on_delete=models.CASCADE,related_name='lines')
    item=models.ForeignKey('menu.Item',on_delete=models.PROTECT)
    qty=models.PositiveIntegerField()
    price_cents=models.PositiveIntegerField()
    class Meta:
        unique_together=('order','item')
