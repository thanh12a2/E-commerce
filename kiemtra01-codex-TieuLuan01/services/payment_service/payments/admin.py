from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order_id", "user_id", "amount", "status", "paid_at", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("=order_id", "=user_id")
    readonly_fields = ("created_at", "updated_at")
