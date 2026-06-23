from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="source_order_id",
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                fields=("source", "source_order_id"),
                name="orders_unique_source_order_id",
            ),
        ),
    ]
