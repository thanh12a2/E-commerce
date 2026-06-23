from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Category, Product
from catalog.seed_data import CATEGORY_FIXTURES, iter_seed_rows


class Command(BaseCommand):
    help = "Seed the unified product catalog with the 10-category taxonomy."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing products before seeding")

    def handle(self, *args, **options):
        fixture_category_slugs = {category["slug"] for category in CATEGORY_FIXTURES}
        fixture_product_keys = set()
        created_count = 0
        updated_count = 0
        created_categories = 0
        deleted_products = 0
        deleted_categories = 0

        with transaction.atomic():
            if options["reset"]:
                deleted_products, _ = Product.objects.all().delete()
                deleted_categories, _ = Category.objects.all().delete()
                self.stdout.write(
                    self.style.WARNING(
                        f"Deleted {deleted_products} product rows and {deleted_categories} category rows before reseeding."
                    )
                )

            for row in iter_seed_rows():
                category_defaults = row["category"]
                category, created_category = Category.objects.update_or_create(
                    slug=category_defaults["slug"],
                    defaults=category_defaults,
                )
                if created_category:
                    created_categories += 1

                product_defaults = row["product"]
                fixture_product_keys.add((category.slug, product_defaults["name"], product_defaults["brand"]))
                _, created = Product.objects.update_or_create(
                    category=category,
                    name=product_defaults["name"],
                    brand=product_defaults["brand"],
                    defaults={
                        "description": product_defaults["description"],
                        "image_url": product_defaults["image_url"],
                        "price": product_defaults["price"],
                        "stock": product_defaults["stock"],
                    },
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            stale_product_ids = [
                product.id
                for product in Product.objects.select_related("category")
                if (
                    product.category.slug,
                    product.name,
                    product.brand,
                )
                not in fixture_product_keys
            ]
            if stale_product_ids:
                deleted_products += Product.objects.filter(id__in=stale_product_ids).delete()[0]

            stale_category_slugs = list(Category.objects.exclude(slug__in=fixture_category_slugs).values_list("slug", flat=True))
            if stale_category_slugs:
                deleted_categories += Category.objects.filter(slug__in=stale_category_slugs).delete()[0]

        self.stdout.write(
            self.style.SUCCESS(
                "Unified product seed complete. "
                f"Categories created: {created_categories}/{len(CATEGORY_FIXTURES)}, deleted: {deleted_categories}. "
                f"Products created: {created_count}, updated: {updated_count}, deleted: {deleted_products}, "
                f"total now: {Product.objects.count()}."
            )
        )
