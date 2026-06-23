from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("chatbot", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="behaviorevent",
            old_name="product_service",
            new_name="category_slug",
        ),
    ]
