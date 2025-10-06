from django.core.cache import cache
from django.db import models

class DiaSemAtendimento(models.Model):
    data = models.DateField("Data", unique=True)
    rotulo = models.CharField("Rótulo", max_length=120)
    repete_anualmente = models.BooleanField("Repete anualmente", default=False,
                                            help_text="Ex.: 25/12 todo ano.")

    class Meta:
        verbose_name = "Dia sem atendimento"
        verbose_name_plural = "Dias sem atendimento"
        ordering = ("data",)

    def __str__(self):
        d = self.data.strftime("%d/%m/%Y")
        if self.repete_anualmente:
            return f"{d} — {self.rotulo} (anual)"
        return f"{d} — {self.rotulo}"


class OrderCutoffSetting(models.Model):
    """
    Singleton-style site setting for lunch order cutoff time.
    Example: 15:00 means: same-day-before-15:00 => order for next eligible day;
                       at/after 15:00         => push base day by +1.
    """
    cutoff_time = models.TimeField(default=None, null=True, blank=True,
                                   help_text="Horário limite diário (hora local). Ex.: 15:00")

    class Meta:
        verbose_name = "Horário limite"
        verbose_name_plural = "Horário limite"

    def __str__(self):
        return self.cutoff_time.strftime("%H:%M") if self.cutoff_time else "Padrão (15:00)"

    @classmethod
    def get_cutoff_time(cls, default_hour=15, default_minute=0):
        """
        Cached read. Returns a Python datetime.time.
        """
        cache_key = "hango.order_cutoff_time"
        value = cache.get(cache_key)
        if value is not None:
            return value

        obj = cls.objects.first()
        if obj and obj.cutoff_time:
            value = obj.cutoff_time
        else:
            from datetime import time
            value = time(default_hour, default_minute)

        cache.set(cache_key, value, 300)  # 5 min cache
        return value
