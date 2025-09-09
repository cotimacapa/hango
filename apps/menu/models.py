from django.db import models


class Category(models.Model):
    name = models.CharField("Nome", max_length=60)
    slug = models.SlugField("Slug", unique=True)
    # Máximo de itens por aluno/dia; em branco = sem limite
    daily_quota = models.PositiveIntegerField("Cota diária", null=True, blank=True)

    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorias"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Item(models.Model):
    name = models.CharField("Nome", max_length=120)
    description = models.TextField("Descrição", blank=True)
    is_active = models.BooleanField("Ativo", default=True)
    category = models.ForeignKey(
        Category,
        verbose_name="Categoria",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        verbose_name = "Item"
        verbose_name_plural = "Itens"

    def __str__(self):
        return self.name
