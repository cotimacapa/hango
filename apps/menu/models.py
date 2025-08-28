from django.db import models
from django.utils.translation import gettext_lazy as _

class Category(models.Model):
    name = models.CharField(max_length=60)
    slug = models.SlugField(unique=True)
    # Max items per student per day; blank = unlimited
    daily_quota = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
        ordering = ["name"]  # (optional, keep if you like)    

    def __str__(self):
        return self.name

class Item(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    category = models.ForeignKey(Category, null=True, blank=True,
                                 on_delete=models.SET_NULL)
    
    class Meta:
        verbose_name = _("Item")
        verbose_name_plural = _("Items")    

    def __str__(self):
        return self.name
