from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BehaviorEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_ref", models.CharField(db_index=True, max_length=120)),
                (
                    "event_type",
                    models.CharField(choices=[("chatbot_ask", "Chatbot ask")], max_length=40),
                ),
                ("product_service", models.CharField(blank=True, max_length=20)),
                ("product_id", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
