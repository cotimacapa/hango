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
