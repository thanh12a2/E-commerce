from django.contrib import admin

from .models import Shipment


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ["id", "order_id", "user_id", "status", "city_or_region", "country", "updated_at"]
    list_filter = ["status", "country", "city_or_region"]
    search_fields = ["order_id", "user_id", "recipient_name", "phone", "address_line"]
