from django.contrib import admin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("sort_order", "name")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "brand", "price", "stock", "updated_at")
    list_filter = ("category", "brand")
    search_fields = ("name", "brand", "description")
    autocomplete_fields = ("category",)
