from django.contrib import admin
from .models import Item, Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "daily_quota")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "description")
