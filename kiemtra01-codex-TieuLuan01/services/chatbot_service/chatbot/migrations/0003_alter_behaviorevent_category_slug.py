from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chatbot", "0002_rename_product_service_category_slug"),
    ]

    operations = [
        migrations.AlterField(
            model_name="behaviorevent",
            name="category_slug",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
