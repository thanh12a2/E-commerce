from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

User = get_user_model()


class StaffLoginTests(TestCase):
    def test_staff_dashboard_redirects_anonymous_users_to_staff_login(self):
        response = self.client.get(reverse("staff_dashboard"))

        self.assertRedirects(response, "/staff/login/?next=/staff/dashboard/")

    def test_staff_login_rejects_superuser_accounts(self):
        User.objects.create_superuser(
            username="root",
            email="root@example.com",
            password="pass12345",
        )

        response = self.client.post(
            reverse("staff_login"),
            {"username": "root", "password": "pass12345"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin accounts should sign in via /admin/.")


class StaffGatewayFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ops",
            email="ops@example.com",
            password="pass12345",
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.client.force_login(self.user)

    def test_staff_items_accepts_legacy_service_query_but_renders_category_filters(self):
        categories = [
            {"id": 4, "slug": "smartphones", "name": "Smartphones"},
            {"id": 5, "slug": "tablets", "name": "Tablets"},
        ]
        items = [
            {
                "service": "smartphones",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "id": 9,
                "name": "Pixel Frame 9",
                "description": "Clean Android phone.",
                "image_url": "https://example.com/pixel.jpg",
                "brand": "Google",
                "price": "899.00",
                "stock": 8,
            }
        ]

        with patch("staff.views.fetch_categories", return_value=categories), patch(
            "staff.views.fetch_products",
            return_value=items,
        ):
            response = self.client.get(reverse("staff_items"), {"service": "smartphones"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_category"], "smartphones")
        self.assertContains(response, "/staff/items/?category=smartphones")
        self.assertContains(response, 'name="return_category" value="smartphones"', html=False)
        self.assertNotContains(response, 'name="return_service"', html=False)

    def test_staff_orders_page_renders_upstream_orders_and_updates_shipping(self):
        orders = [
            {
                "id": 21,
                "user_id": 7,
                "payment_status": "paid",
                "shipping_status": "preparing",
                "total_amount": "199.00",
                "created_at": "2026-04-20T01:00:00Z",
                "shipping": {
                    "recipient_name": "Nguyen Van A",
                    "phone": "0123456789",
                    "city_or_region": "HCMC",
                    "country": "VN",
                },
                "items": [{"product_name": "QuietBeat ANC", "quantity": 1}],
            }
        ]

        with patch("staff.views.fetch_staff_orders", return_value=orders):
            response = self.client.get(reverse("staff_orders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "QuietBeat ANC")
        self.assertContains(response, "PREPARING")

        with patch("staff.views.update_shipping_status", return_value=(True, {"id": 21}, None)):
            post_response = self.client.post(
                reverse("staff_orders"),
                {"order_id": 21, "shipping_status": "shipped"},
            )

        self.assertRedirects(post_response, "/staff/orders/")

    def test_seed_staff_demo_data_creates_customers_and_orders_via_service_helpers(self):
        products = [
            {
                "service": "ultrabooks",
                "category_slug": "ultrabooks",
                "category_name": "Ultrabooks",
                "id": 31,
                "name": "AirLite 13",
                "description": "Portable laptop.",
                "image_url": "https://example.com/airlite.jpg",
                "image_fallback_url": "https://example.com/airlite-fallback.jpg",
                "brand": "ASUS",
                "price": "999.00",
                "stock": 8,
            },
            {
                "service": "smartphones",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "id": 41,
                "name": "Pixel Frame 9",
                "description": "Camera phone.",
                "image_url": "https://example.com/pixel.jpg",
                "image_fallback_url": "https://example.com/pixel-fallback.jpg",
                "brand": "Google",
                "price": "899.00",
                "stock": 12,
            },
            {
                "service": "audio",
                "category_slug": "audio",
                "category_name": "Audio",
                "id": 51,
                "name": "QuietBeat ANC",
                "description": "Headphones.",
                "image_url": "https://example.com/quietbeat.jpg",
                "image_fallback_url": "https://example.com/quietbeat-fallback.jpg",
                "brand": "Sony",
                "price": "249.00",
                "stock": 16,
            },
            {
                "service": "tablets",
                "category_slug": "tablets",
                "category_name": "Tablets",
                "id": 61,
                "name": "Slate Pro 11",
                "description": "Tablet.",
                "image_url": "https://example.com/slate.jpg",
                "image_fallback_url": "https://example.com/slate-fallback.jpg",
                "brand": "Apple",
                "price": "899.00",
                "stock": 10,
            },
            {
                "service": "bags-stands",
                "category_slug": "bags-stands",
                "category_name": "Bags & Stands",
                "id": 71,
                "name": "LiftStand Fold",
                "description": "Stand.",
                "image_url": "https://example.com/stand.jpg",
                "image_fallback_url": "https://example.com/stand-fallback.jpg",
                "brand": "MOFT",
                "price": "59.00",
                "stock": 24,
            },
            {
                "service": "chargers-cables",
                "category_slug": "chargers-cables",
                "category_name": "Chargers & Cables",
                "id": 81,
                "name": "PowerBrick 65W",
                "description": "Charger.",
                "image_url": "https://example.com/charger.jpg",
                "image_fallback_url": "https://example.com/charger-fallback.jpg",
                "brand": "Anker",
                "price": "49.00",
                "stock": 50,
            },
            {
                "service": "keyboards-mice",
                "category_slug": "keyboards-mice",
                "category_name": "Keyboards & Mice",
                "id": 91,
                "name": "DeskMouse Master",
                "description": "Mouse.",
                "image_url": "https://example.com/mouse.jpg",
                "image_fallback_url": "https://example.com/mouse-fallback.jpg",
                "brand": "Logitech",
                "price": "109.00",
                "stock": 30,
            },
            {
                "service": "smartwatches",
                "category_slug": "smartwatches",
                "category_name": "Smartwatches",
                "id": 101,
                "name": "Pulse Watch 9",
                "description": "Watch.",
                "image_url": "https://example.com/watch.jpg",
                "image_fallback_url": "https://example.com/watch-fallback.jpg",
                "brand": "Apple",
                "price": "399.00",
                "stock": 14,
            },
        ]

        with patch("staff.management.commands.seed_staff_demo_data.fetch_products", return_value=products), patch(
            "staff.management.commands.seed_staff_demo_data.list_orders",
            return_value=[],
        ), patch(
            "staff.management.commands.seed_staff_demo_data.add_to_cart",
            return_value=(True, {"id": 1}, None),
        ) as add_to_cart_mock, patch(
            "staff.management.commands.seed_staff_demo_data.checkout_order",
            return_value=(True, {"id": 701}, None),
        ) as checkout_mock, patch(
            "staff.management.commands.seed_staff_demo_data.pay_order",
            return_value=(True, {"id": 701}, None),
        ) as pay_mock, patch(
            "staff.management.commands.seed_staff_demo_data.update_shipping_status",
            return_value=(True, {"id": 701}, None),
        ) as shipping_mock:
            call_command(
                "seed_staff_demo_data",
                customers=2,
                min_orders=1,
                max_orders=1,
                seed=7,
                prefix="synthetic_",
            )

        self.assertEqual(User.objects.filter(username__startswith="synthetic_").count(), 2)
        self.assertGreaterEqual(add_to_cart_mock.call_count, 2)
        self.assertEqual(checkout_mock.call_count, 2)
        self.assertGreaterEqual(pay_mock.call_count, 1)
        self.assertGreaterEqual(shipping_mock.call_count, 1)
