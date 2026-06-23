from django.db import models


class Shipment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PREPARING = "preparing"
    STATUS_SHIPPED = "shipped"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PREPARING, "Preparing"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    STATUS_VALUES = {choice for choice, _ in STATUS_CHOICES}
    STATUS_TRANSITIONS = {
        STATUS_PENDING: {
            STATUS_PENDING,
            STATUS_PREPARING,
            STATUS_SHIPPED,
            STATUS_DELIVERED,
            STATUS_CANCELLED,
        },
        STATUS_PREPARING: {
            STATUS_PREPARING,
            STATUS_SHIPPED,
            STATUS_DELIVERED,
            STATUS_CANCELLED,
        },
        STATUS_SHIPPED: {STATUS_SHIPPED, STATUS_DELIVERED},
        STATUS_DELIVERED: {STATUS_DELIVERED},
        STATUS_CANCELLED: {STATUS_CANCELLED},
    }

    order_id = models.PositiveIntegerField(unique=True)
    user_id = models.PositiveIntegerField(db_index=True)
    recipient_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=40)
    address_line = models.CharField(max_length=255)
    city_or_region = models.CharField(max_length=120)
    postal_code = models.CharField(max_length=40)
    country = models.CharField(max_length=120)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user_id", "status"], name="shipments_user_status_idx"),
            models.Index(fields=["status", "updated_at"], name="shipments_status_updated_idx"),
        ]

    def can_update_status(self, new_status):
        if new_status not in self.STATUS_VALUES:
            return False, "Invalid shipment status."
        allowed_statuses = self.STATUS_TRANSITIONS.get(self.status, {self.status})
        if new_status not in allowed_statuses:
            return False, f"Cannot move shipment from {self.status} to {new_status}."
        return True, ""
