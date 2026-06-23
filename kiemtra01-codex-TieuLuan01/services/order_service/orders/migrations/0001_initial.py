from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CartItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category_slug", models.SlugField(blank=True, max_length=120)),
                ("category_name", models.CharField(blank=True, max_length=120)),
                ("product_id", models.PositiveIntegerField(default=0)),
                ("product_name", models.CharField(max_length=255)),
                ("product_brand", models.CharField(blank=True, max_length=120)),
                ("product_image_url", models.URLField(blank=True)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("user_id", models.PositiveIntegerField(db_index=True)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-updated_at"], "unique_together": {("user_id", "category_slug", "product_id")}},
        ),
        migrations.CreateModel(
            name="CompareItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category_slug", models.SlugField(blank=True, max_length=120)),
                ("category_name", models.CharField(blank=True, max_length=120)),
                ("product_id", models.PositiveIntegerField(default=0)),
                ("product_name", models.CharField(max_length=255)),
                ("product_brand", models.CharField(blank=True, max_length=120)),
                ("product_image_url", models.URLField(blank=True)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("user_id", models.PositiveIntegerField(db_index=True)),
                ("stock", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"], "unique_together": {("user_id", "category_slug", "product_id")}},
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.PositiveIntegerField(db_index=True)),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "payment_status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("paid", "Paid"), ("cancelled", "Cancelled")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "shipping_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("preparing", "Preparing"),
                            ("shipped", "Shipped"),
                            ("delivered", "Delivered"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("source", models.CharField(choices=[("live", "Live"), ("legacy_import", "Legacy import")], default="live", max_length=20)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="SavedItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category_slug", models.SlugField(blank=True, max_length=120)),
                ("category_name", models.CharField(blank=True, max_length=120)),
                ("product_id", models.PositiveIntegerField(default=0)),
                ("product_name", models.CharField(max_length=255)),
                ("product_brand", models.CharField(blank=True, max_length=120)),
                ("product_image_url", models.URLField(blank=True)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("user_id", models.PositiveIntegerField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"], "unique_together": {("user_id", "category_slug", "product_id")}},
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category_slug", models.SlugField(blank=True, max_length=120)),
                ("category_name", models.CharField(blank=True, max_length=120)),
                ("product_id", models.PositiveIntegerField(default=0)),
                ("product_name", models.CharField(max_length=255)),
                ("product_brand", models.CharField(blank=True, max_length=120)),
                ("product_image_url", models.URLField(blank=True)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("quantity", models.PositiveIntegerField(default=1)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="orders.order",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="OrderShipping",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recipient_name", models.CharField(max_length=120)),
                ("phone", models.CharField(max_length=40)),
                ("address_line", models.CharField(max_length=255)),
                ("city_or_region", models.CharField(max_length=120)),
                ("postal_code", models.CharField(max_length=40)),
                ("country", models.CharField(max_length=120)),
                ("note", models.TextField(blank=True)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shipping",
                        to="orders.order",
                    ),
                ),
            ],
        ),
    ]
