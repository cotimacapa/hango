from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from .models import OrderCutoffSetting

@receiver(post_save, sender=OrderCutoffSetting)
def clear_cutoff_cache(sender, **kwargs):
    cache.delete("hango.order_cutoff_time")
