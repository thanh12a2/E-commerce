from django.contrib import admin

from .models import CartItem, CompareItem, Order, OrderItem, OrderShipping, SavedItem


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("user_id", "product_name", "category_slug", "quantity", "unit_price", "updated_at")
    list_filter = ("category_slug",)
    search_fields = ("product_name", "product_brand", "user_id")


@admin.register(SavedItem)
class SavedItemAdmin(admin.ModelAdmin):
    list_display = ("user_id", "product_name", "category_slug", "unit_price", "created_at")
    list_filter = ("category_slug",)
    search_fields = ("product_name", "product_brand", "user_id")


@admin.register(CompareItem)
class CompareItemAdmin(admin.ModelAdmin):
    list_display = ("user_id", "product_name", "category_slug", "unit_price", "stock", "created_at")
    list_filter = ("category_slug",)
    search_fields = ("product_name", "product_brand", "user_id")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderShippingInline(admin.StackedInline):
    model = OrderShipping
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "payment_status", "shipping_status", "source", "source_order_id", "total_amount", "created_at")
    list_filter = ("payment_status", "shipping_status", "source")
    search_fields = ("id", "user_id", "source_order_id")
    inlines = [OrderShippingInline, OrderItemInline]
