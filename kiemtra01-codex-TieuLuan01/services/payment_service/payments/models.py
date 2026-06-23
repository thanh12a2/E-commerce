from django.db import models


class Payment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    TERMINAL_STATUSES = {STATUS_PAID, STATUS_FAILED, STATUS_CANCELLED}

    order_id = models.PositiveIntegerField(unique=True)
    user_id = models.PositiveIntegerField(db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user_id", "status"], name="payments_user_status_idx"),
        ]

    def can_confirm(self):
        if self.status != self.STATUS_PENDING:
            return False, "Only pending payments can be confirmed."
        return True, ""

    def can_cancel(self):
        if self.status != self.STATUS_PENDING:
            return False, "Only pending payments can be cancelled."
        return True, ""
