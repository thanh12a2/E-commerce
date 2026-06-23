from django.db import models


class ProductSnapshotMixin(models.Model):
    category_slug = models.SlugField(max_length=120, blank=True)
    category_name = models.CharField(max_length=120, blank=True)
    product_id = models.PositiveIntegerField(default=0)
    product_name = models.CharField(max_length=255)
    product_brand = models.CharField(max_length=120, blank=True)
    product_image_url = models.URLField(blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        abstract = True


class CartItem(ProductSnapshotMixin):
    user_id = models.PositiveIntegerField(db_index=True)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = ("user_id", "category_slug", "product_id")

    @property
    def total_price(self):
        return self.unit_price * self.quantity


class SavedItem(ProductSnapshotMixin):
    user_id = models.PositiveIntegerField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("user_id", "category_slug", "product_id")


class CompareItem(ProductSnapshotMixin):
    user_id = models.PositiveIntegerField(db_index=True)
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("user_id", "category_slug", "product_id")


class Order(models.Model):
    SOURCE_LIVE = "live"
    SOURCE_LEGACY_IMPORT = "legacy_import"
    SOURCE_CHOICES = [
        (SOURCE_LIVE, "Live"),
        (SOURCE_LEGACY_IMPORT, "Legacy import"),
    ]

    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_CANCELLED = "cancelled"
    PAYMENT_CHOICES = [
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_CANCELLED, "Cancelled"),
    ]

    SHIPPING_PENDING = "pending"
    SHIPPING_PREPARING = "preparing"
    SHIPPING_SHIPPED = "shipped"
    SHIPPING_DELIVERED = "delivered"
    SHIPPING_CANCELLED = "cancelled"
    SHIPPING_CHOICES = [
        (SHIPPING_PENDING, "Pending"),
        (SHIPPING_PREPARING, "Preparing"),
        (SHIPPING_SHIPPED, "Shipped"),
        (SHIPPING_DELIVERED, "Delivered"),
        (SHIPPING_CANCELLED, "Cancelled"),
    ]
    PAYMENT_VALUES = {choice for choice, _ in PAYMENT_CHOICES}
    SHIPPING_VALUES = {choice for choice, _ in SHIPPING_CHOICES}
    SHIPPING_TRANSITIONS = {
        SHIPPING_PENDING: {
            SHIPPING_PENDING,
            SHIPPING_PREPARING,
            SHIPPING_SHIPPED,
            SHIPPING_DELIVERED,
            SHIPPING_CANCELLED,
        },
        SHIPPING_PREPARING: {
            SHIPPING_PREPARING,
            SHIPPING_SHIPPED,
            SHIPPING_DELIVERED,
            SHIPPING_CANCELLED,
        },
        SHIPPING_SHIPPED: {SHIPPING_SHIPPED, SHIPPING_DELIVERED},
        SHIPPING_DELIVERED: {SHIPPING_DELIVERED},
        SHIPPING_CANCELLED: {SHIPPING_CANCELLED},
    }

    user_id = models.PositiveIntegerField(db_index=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_PENDING)
    shipping_status = models.CharField(max_length=20, choices=SHIPPING_CHOICES, default=SHIPPING_PENDING)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_LIVE)
    source_order_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_order_id"],
                name="orders_unique_source_order_id",
            )
        ]

    def can_pay(self):
        if self.payment_status != self.PAYMENT_PENDING:
            return False, "Only pending orders can be paid."
        if self.shipping_status == self.SHIPPING_CANCELLED:
            return False, "Cancelled shipments cannot be paid."
        return True, ""

    def can_update_shipping_status(self, new_status):
        if new_status not in self.SHIPPING_VALUES:
            return False, "Invalid shipping status."
        if new_status in {
            self.SHIPPING_PREPARING,
            self.SHIPPING_SHIPPED,
            self.SHIPPING_DELIVERED,
        } and self.payment_status != self.PAYMENT_PAID:
            return False, "Only paid orders can advance shipping."
        allowed_statuses = self.SHIPPING_TRANSITIONS.get(self.shipping_status, {self.shipping_status})
        if new_status not in allowed_statuses:
            return (
                False,
                f"Cannot move shipping from {self.shipping_status} to {new_status}.",
            )
        return True, ""


class OrderShipping(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="shipping")
    recipient_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=40)
    address_line = models.CharField(max_length=255)
    city_or_region = models.CharField(max_length=120)
    postal_code = models.CharField(max_length=40)
    country = models.CharField(max_length=120)
    note = models.TextField(blank=True)


class OrderItem(ProductSnapshotMixin):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["id"]

    @property
    def total_price(self):
        return self.unit_price * self.quantity
