from django.db import models
class Item(models.Model):
    name=models.CharField(max_length=120)
    description=models.TextField(blank=True)
    price_cents=models.PositiveIntegerField()
    is_active=models.BooleanField(default=True)
    def __str__(self): return self.name
    @property
    def price_display(self): return f"R${self.price_cents/100:.2f}"
