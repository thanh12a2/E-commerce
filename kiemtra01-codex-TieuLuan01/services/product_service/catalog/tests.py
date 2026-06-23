from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Category, Product


class ProductCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_products", "--reset")

    def setUp(self):
        self.client = APIClient()

    def test_seed_creates_expected_taxonomy(self):
        self.assertEqual(Category.objects.count(), 10)
        self.assertEqual(Product.objects.count(), 100)
        self.assertTrue(Category.objects.filter(slug="business-laptops", is_active=True).exists())
        self.assertEqual(Product.objects.filter(category__slug="business-laptops").count(), 10)

    def test_category_endpoint_lists_all_active_categories(self):
        response = self.client.get("/api/categories/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 10)
        self.assertEqual(payload[0]["slug"], "business-laptops")

    def test_product_filters_support_category_search_brand_price_and_stock(self):
        response = self.client.get(
            "/api/products/",
            {
                "category": "smartphones",
                "search": "Pixel",
                "brand": "Google",
                "min_price": "800",
                "max_price": "1200",
                "in_stock": "true",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(len(payload), 1)
        self.assertTrue(all(item["category_slug"] == "smartphones" for item in payload))
        self.assertTrue(all("Pixel" in item["name"] for item in payload))
        self.assertTrue(all(item["category_name"] == "Smartphones" for item in payload))

        audio = Category.objects.get(slug="audio")
        out_of_stock = Product.objects.filter(category=audio).order_by("id").first()
        out_of_stock.stock = 0
        out_of_stock.save(update_fields=["stock"])

        zero_stock_response = self.client.get(
            "/api/products/",
            {
                "category": str(audio.id),
                "in_stock": "false",
            },
        )
        self.assertEqual(zero_stock_response.status_code, 200)
        zero_stock_payload = zero_stock_response.json()
        self.assertEqual(len(zero_stock_payload), 1)
        self.assertEqual(zero_stock_payload[0]["id"], out_of_stock.id)
        self.assertEqual(zero_stock_payload[0]["category_slug"], "audio")

    def test_product_detail_includes_category_identity_fields(self):
        product = Product.objects.get(name="Pixel Frame 9", brand="Google")

        response = self.client.get(f"/api/products/{product.id}/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["category"], product.category_id)
        self.assertEqual(payload["category_slug"], "smartphones")
        self.assertEqual(payload["category_name"], "Smartphones")

    def test_staff_protected_writes_require_staff_key(self):
        category = Category.objects.get(slug="audio")
        payload = {
            "category": category.id,
            "name": "Studio Voice Mini",
            "brand": "Rode",
            "description": "Compact creator microphone.",
            "image_url": "https://example.com/mic.jpg",
            "price": "129.00",
            "stock": 14,
        }

        forbidden = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(forbidden.status_code, 403)

        created = self.client.post(
            "/api/products/",
            payload,
            format="json",
            HTTP_X_STAFF_KEY="dev-staff-key",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["category_slug"], "audio")

        product_id = created.json()["id"]
        patch_forbidden = self.client.patch(
            f"/api/products/{product_id}/",
            {"stock": 0},
            format="json",
        )
        self.assertEqual(patch_forbidden.status_code, 403)

        patch_allowed = self.client.patch(
            f"/api/products/{product_id}/",
            {"stock": 0},
            format="json",
            HTTP_X_STAFF_KEY="dev-staff-key",
        )
        self.assertEqual(patch_allowed.status_code, 200)
        self.assertEqual(patch_allowed.json()["stock"], 0)

    def test_seed_command_is_deterministic_without_reset(self):
        extra_category = Category.objects.create(
            name="Seasonal Deals",
            slug="seasonal-deals",
            description="Temporary marketing category.",
            hero_image_url="https://example.com/seasonal.jpg",
            sort_order=999,
            is_active=True,
        )
        Product.objects.create(
            category=extra_category,
            name="Flash Bundle",
            brand="Promo",
            description="Temporary product that should be pruned by seed sync.",
            image_url="https://example.com/flash.jpg",
            price="9.99",
            stock=3,
        )
        Product.objects.create(
            category=Category.objects.get(slug="audio"),
            name="Studio Voice Mini",
            brand="Rode",
            description="Manual insert that should be removed by deterministic seed.",
            image_url="https://example.com/manual.jpg",
            price="129.00",
            stock=14,
        )

        call_command("seed_products")

        self.assertEqual(Category.objects.count(), 10)
        self.assertEqual(Product.objects.count(), 100)
        self.assertFalse(Category.objects.filter(slug="seasonal-deals").exists())
        self.assertFalse(Product.objects.filter(name="Flash Bundle", brand="Promo").exists())
        self.assertFalse(Product.objects.filter(name="Studio Voice Mini", brand="Rode").exists())
