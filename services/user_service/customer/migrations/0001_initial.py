from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BlogPost",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=220)),
                ("slug", models.SlugField(unique=True)),
                ("category", models.CharField(max_length=80)),
                ("author", models.CharField(max_length=120)),
                ("excerpt", models.TextField()),
                ("body", models.TextField()),
                ("hero_image_url", models.URLField(blank=True)),
                ("published_at", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-published_at", "-id"]},
        ),
        migrations.CreateModel(
            name="Testimonial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("role", models.CharField(max_length=120)),
                ("rating", models.PositiveSmallIntegerField(default=5)),
                ("quote", models.TextField()),
                ("avatar_url", models.URLField(blank=True)),
                ("is_featured", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="LegacyUserMapping",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("legacy_source", models.CharField(choices=[("customer", "Customer"), ("staff", "Staff")], max_length=20)),
                ("legacy_user_id", models.PositiveIntegerField()),
                ("legacy_username", models.CharField(blank=True, max_length=150)),
                ("legacy_email", models.EmailField(blank=True, max_length=254)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="legacy_mappings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["legacy_source", "legacy_user_id"],
                "unique_together": {("legacy_source", "legacy_user_id")},
            },
        ),
    ]
