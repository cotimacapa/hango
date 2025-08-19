from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=60)
    slug = models.SlugField(unique=True)
    # Max items per student per day; blank = unlimited
    daily_quota = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.name

class Item(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    category = models.ForeignKey(Category, null=True, blank=True,
                                 on_delete=models.SET_NULL)

    def __str__(self):
        return self.name
