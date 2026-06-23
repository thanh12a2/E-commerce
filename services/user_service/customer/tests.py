from io import StringIO
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from .legacy_users import merge_legacy_accounts
from .models import LegacyUserMapping
from .services import add_to_cart, fetch_products, request_chatbot_reply

User = get_user_model()


class LegacyUserMergeTests(TestCase):
    def test_merge_prefers_staff_on_conflict_and_unions_roles(self):
        merged = merge_legacy_accounts(
            [
                {
                    "id": 1,
                    "source": "customer",
                    "username": "alex",
                    "email": "alex@example.com",
                    "password": "cust-hash",
                    "first_name": "Alex",
                    "last_name": "Customer",
                    "is_staff": False,
                    "is_superuser": False,
                },
                {
                    "id": 3,
                    "source": "staff",
                    "username": "alex.staff",
                    "email": "alex@example.com",
                    "password": "staff-hash",
                    "first_name": "Alex",
                    "last_name": "Staff",
                    "is_staff": True,
                    "is_superuser": False,
                },
            ]
        )

        self.assertEqual(len(merged), 1)
        account = merged[0]
        self.assertEqual(account["username"], "alex.staff")
        self.assertEqual(account["password"], "staff-hash")
        self.assertTrue(account["is_staff"])
        self.assertFalse(account["is_superuser"])
        self.assertEqual(len(account["legacy_rows"]), 2)

    def test_merge_falls_back_to_username_when_email_missing(self):
        merged = merge_legacy_accounts(
            [
                {
                    "id": 10,
                    "source": "customer",
                    "username": "kim",
                    "email": "",
                    "password": "cust",
                    "first_name": "Kim",
                    "last_name": "One",
                    "is_staff": False,
                    "is_superuser": False,
                },
                {
                    "id": 11,
                    "source": "staff",
                    "username": "kim",
                    "email": "",
                    "password": "staff",
                    "first_name": "Kim",
                    "last_name": "Two",
                    "is_staff": True,
                    "is_superuser": False,
                },
            ]
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["username"], "kim")
        self.assertTrue(merged[0]["is_staff"])


class MigrateLegacyUsersCommandTests(TestCase):
    def test_command_merges_existing_shared_auth_user_by_email_before_username(self):
        shared_user = User.objects.create_user(
            username="shared-auth",
            email="alex@example.com",
            password="pass12345",
        )
        colliding_user = User.objects.create_user(
            username="alex.staff",
            email="other@example.com",
            password="pass12345",
        )

        stdout = StringIO()
        customer_rows = [
            {
                "id": 1,
                "source": "customer",
                "username": "alex",
                "email": "alex@example.com",
                "password": "cust-hash",
                "first_name": "Alex",
                "last_name": "Customer",
                "is_staff": False,
                "is_superuser": False,
            }
        ]
        staff_rows = [
            {
                "id": 3,
                "source": "staff",
                "username": "alex.staff",
                "email": "alex@example.com",
                "password": "staff-hash",
                "first_name": "Alex",
                "last_name": "Staff",
                "is_staff": True,
                "is_superuser": False,
            }
        ]

        with patch(
            "customer.management.commands.migrate_legacy_users._fetch_legacy_users",
            side_effect=[customer_rows, staff_rows],
        ):
            call_command("migrate_legacy_users", stdout=stdout)

        shared_user.refresh_from_db()
        colliding_user.refresh_from_db()

        self.assertEqual(shared_user.username, "shared-auth")
        self.assertEqual(shared_user.email, "alex@example.com")
        self.assertEqual(shared_user.password, "staff-hash")
        self.assertEqual(shared_user.first_name, "Alex")
        self.assertEqual(shared_user.last_name, "Staff")
        self.assertTrue(shared_user.is_staff)
        self.assertFalse(shared_user.is_superuser)
        self.assertEqual(colliding_user.username, "alex.staff")
        self.assertEqual(colliding_user.email, "other@example.com")
        self.assertEqual(LegacyUserMapping.objects.filter(user=shared_user).count(), 2)

        mapping = LegacyUserMapping.objects.get(legacy_source="staff", legacy_user_id=3)
        self.assertIn("existing_match=email", mapping.note)
        self.assertIn("primary_role=staff", mapping.note)
        self.assertIn("username collision in shared auth", mapping.note)

        output = stdout.getvalue()
        self.assertIn("matched_email=1", output)
        self.assertIn("conflicts=1", output)


class SharedAuthFlowTests(TestCase):
    def test_customer_login_redirects_staff_user_to_staff_login(self):
        user = User.objects.create_user(
            username="ops",
            email="ops@example.com",
            password="pass12345",
        )
        user.is_staff = True
        user.save(update_fields=["is_staff"])

        response = self.client.post(
            reverse("customer_login"),
            {"username": "ops", "password": "pass12345"},
        )

        self.assertRedirects(response, reverse("staff_login"))

    def test_staff_session_cannot_render_customer_orders_as_empty_history(self):
        user = User.objects.create_user(
            username="ops-view",
            email="ops-view@example.com",
            password="pass12345",
        )
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        self.client.force_login(user)

        response = self.client.get(reverse("customer_orders"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('customer_login')}?next={reverse('customer_orders')}")

    def test_customer_and_staff_sessions_can_coexist_in_one_browser(self):
        customer = User.objects.create_user(
            username="buyer-one",
            email="buyer-one@example.com",
            password="pass12345",
        )
        staff = User.objects.create_user(
            username="ops-one",
            email="ops-one@example.com",
            password="pass12345",
        )
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])

        customer_response = self.client.post(
            reverse("customer_login"),
            {"username": customer.username, "password": "pass12345"},
        )
        self.assertEqual(customer_response.status_code, 302)
        self.assertEqual(customer_response["Location"], reverse("customer_dashboard"))
        self.assertIn("customer_sessionid", self.client.cookies)

        staff_response = self.client.post(
            reverse("staff_login"),
            {"username": staff.username, "password": "pass12345"},
        )
        self.assertEqual(staff_response.status_code, 302)
        self.assertEqual(staff_response["Location"], reverse("staff_dashboard"))
        self.assertIn("staff_sessionid", self.client.cookies)

        with patch("customer.views.fetch_categories", return_value=[]), patch(
            "customer.views.list_orders",
            return_value=[],
        ) as list_orders_mock:
            response = self.client.get(reverse("customer_orders"))

        self.assertEqual(response.status_code, 200)
        list_orders_mock.assert_called_once_with(customer.id)


class JwtAuthApiTests(TestCase):
    def setUp(self):
        self.api_client = APIClient()

    def test_register_creates_customer_account_and_returns_tokens(self):
        response = self.api_client.post(
            reverse("api_auth_register"),
            {
                "username": "api-customer",
                "email": "api-customer@example.com",
                "password": "pass12345",
                "confirm_password": "pass12345",
                "first_name": "Api",
                "last_name": "Customer",
                "is_staff": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertIn("access", payload)
        self.assertIn("refresh", payload)
        self.assertEqual(payload["user"]["username"], "api-customer")
        self.assertEqual(payload["user"]["role"], "customer")
        self.assertEqual(payload["user"]["scopes"], ["customer"])
        self.assertFalse(payload["user"]["is_staff"])
        user = User.objects.get(username="api-customer")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_token_returns_jwt_pair_with_user_role_payload(self):
        User.objects.create_user(
            username="api-customer",
            email="api-customer@example.com",
            password="pass12345",
        )

        response = self.api_client.post(
            reverse("api_auth_token"),
            {"username": "api-customer", "password": "pass12345"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("access", payload)
        self.assertIn("refresh", payload)
        self.assertEqual(payload["user"]["role"], "customer")
        access = AccessToken(payload["access"])
        self.assertEqual(access["role"], "customer")
        self.assertEqual(access["scopes"], ["customer"])
        self.assertFalse(access["is_staff"])

    def test_refresh_token_and_me_endpoint_use_jwt(self):
        User.objects.create_user(
            username="api-customer",
            email="api-customer@example.com",
            password="pass12345",
        )
        token_response = self.api_client.post(
            reverse("api_auth_token"),
            {"username": "api-customer", "password": "pass12345"},
            format="json",
        )
        refresh = token_response.json()["refresh"]

        refresh_response = self.api_client.post(
            reverse("api_auth_token_refresh"),
            {"refresh": refresh},
            format="json",
        )

        self.assertEqual(refresh_response.status_code, 200)
        access = refresh_response.json()["access"]
        me_response = self.api_client.get(
            reverse("api_auth_me"),
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )

        self.assertEqual(me_response.status_code, 200)
        payload = me_response.json()["user"]
        self.assertEqual(payload["username"], "api-customer")
        self.assertEqual(payload["role"], "customer")
        self.assertEqual(payload["scopes"], ["customer"])

    def test_staff_flags_are_exposed_for_existing_staff_accounts(self):
        user = User.objects.create_user(
            username="api-staff",
            email="api-staff@example.com",
            password="pass12345",
        )
        user.is_staff = True
        user.save(update_fields=["is_staff"])

        response = self.api_client.post(
            reverse("api_auth_token"),
            {"username": "api-staff", "password": "pass12345"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["user"]["is_staff"])
        self.assertEqual(payload["user"]["role"], "staff")
        self.assertEqual(payload["user"]["scopes"], ["staff"])
        access = AccessToken(payload["access"])
        self.assertTrue(access["is_staff"])
        self.assertEqual(access["role"], "staff")

    def test_session_login_still_works_for_customer_ui(self):
        User.objects.create_user(
            username="session-customer",
            email="session-customer@example.com",
            password="pass12345",
        )

        response = self.client.post(
            reverse("customer_login"),
            {"username": "session-customer", "password": "pass12345"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("customer_dashboard"))


class CustomerGatewayFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="customer1",
            email="customer1@example.com",
            password="pass12345",
        )
        self.client.force_login(self.user)

    def test_gateway_dashboard_exposes_dedicated_workspace_and_code_zone(self):
        response = self.client.get(reverse("customer_gateway_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API Gateway Workspace")
        self.assertContains(response, "Dedicated code zone")
        self.assertContains(response, "services/user_service/customer/api_gateway/definitions.py")
        self.assertContains(response, "/customer/chatbot/reply/")

    def test_gateway_api_index_returns_sections_stats_and_resolved_urls(self):
        response = self.client.get(reverse("customer_gateway_apis"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stats"]["service_count"], 6)
        self.assertGreaterEqual(payload["stats"]["route_count"], 7)
        self.assertIn("sections", payload)
        self.assertEqual(payload["gateway_dashboard_url"], "http://testserver/gateway/")
        self.assertEqual(payload["services"]["payment_service"]["internal"], "http://payment-service:8000")
        self.assertEqual(payload["services"]["shipping_service"]["internal"], "http://shipping-service:8000")
        chatbot_route = next(route for route in payload["routes"] if route["id"] == "chatbot-proxy")
        self.assertEqual(chatbot_route["upstream"], "chatbot_service")
        self.assertEqual(chatbot_route["public_urls"][0], "http://testserver/customer/chatbot/reply/")

    def test_dashboard_accepts_legacy_service_query_but_renders_category_slug_links(self):
        categories = [
            {
                "id": 4,
                "slug": "smartphones",
                "name": "Smartphones",
                "description": "Phones for communication and capture.",
                "hero_image_url": "https://example.com/smartphones.jpg",
                "sort_order": 40,
            },
            {
                "id": 5,
                "slug": "tablets",
                "name": "Tablets",
                "description": "Portable tablets for study and work.",
                "hero_image_url": "https://example.com/tablets.jpg",
                "sort_order": 50,
            },
        ]
        products = [
            {
                "service": "smartphones",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "id": 42,
                "name": "Pixel Frame 9",
                "description": "Clean Android experience.",
                "image_url": "https://example.com/pixel.jpg",
                "brand": "Google",
                "price": "899.00",
                "stock": 8,
            }
        ]

        with patch("customer.views.fetch_categories", return_value=categories), patch(
            "customer.views.fetch_products",
            side_effect=lambda filters=None: list(products),
        ), patch("customer.views.list_saved_items", return_value=[]), patch(
            "customer.views.list_cart_items",
            return_value=[],
        ):
            response = self.client.get(reverse("customer_dashboard"), {"service": "mobile"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filters"]["category"], "mobile")
        self.assertContains(response, "/customer/dashboard/?category=smartphones")
        self.assertNotContains(response, "/customer/dashboard/?category=laptop")
        self.assertContains(response, '/customer/products/smartphones/42/')
        self.assertContains(response, 'name="category_slug" value="smartphones"', html=False)

    def test_product_detail_uses_category_slug_in_forms_recommendations_and_chat_widget(self):
        product = {
            "service": "tablets",
            "category_slug": "tablets",
            "category_name": "Tablets",
            "id": 55,
            "name": "Slate Pro 11",
            "description": "Tablet for note-taking.",
            "image_url": "https://example.com/tablet.jpg",
            "brand": "Apple",
            "price": "899.00",
            "stock": 5,
        }
        related_products = [
            {
                "service": "tablets",
                "category_slug": "tablets",
                "category_name": "Tablets",
                "id": 77,
                "name": "Pad Air Neo",
                "description": "Value tablet.",
                "image_url": "https://example.com/neo.jpg",
                "brand": "Xiaomi",
                "price": "499.00",
                "stock": 12,
            }
        ]

        with patch("customer.views.fetch_categories", return_value=[]), patch(
            "customer.views.fetch_category_lookup",
            return_value={"tablets": {"hero_image_url": "https://example.com/tablets-hero.jpg"}},
        ), patch("customer.views.fetch_product_detail", return_value=product), patch(
            "customer.views.recommend_products_for_detail",
            return_value=related_products,
        ), patch("customer.views.list_cart_items", return_value=[]), patch(
            "customer.views.list_saved_items",
            return_value=[],
        ), patch("customer.views.list_compare_items", return_value=[]):
            response = self.client.get(reverse("customer_product_detail", args=["tablets", 55]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="category_slug" value="tablets"', html=False)
        self.assertContains(response, 'data-category-slug="tablets"', html=False)
        self.assertContains(response, "/customer/products/tablets/77/")

    def test_chatbot_proxy_keeps_phase_one_response_shape(self):
        with patch(
            "customer.views.request_chatbot_reply",
            return_value={
                "answer": "Hybrid chatbot reply.",
                "recommendations": [
                    {
                        "service": "smartphones",
                        "category_slug": "smartphones",
                        "category_name": "Smartphones",
                        "id": 42,
                        "name": "Pixel Frame 9",
                        "brand": "Google",
                        "price": "899.00",
                        "stock": 8,
                        "image_url": "https://example.com/pixel.jpg",
                    }
                ],
                "citations": [
                    {"label": "Behavior graph", "detail": "Behavior graph for Smartphones", "url": "/customer/dashboard/"}
                ],
                "source": "gemma_4_31b",
                "fallback_used": False,
                "error_code": None,
                "provider": None,
            },
        ), patch(
            "customer.views.build_user_context_payload",
            return_value={"cart_items": [], "saved_items": [], "recent_paid_items": []},
        ):
            response = self.client.post(
                reverse("customer_chatbot_reply"),
                {"message": "Need a smartphone for travel photos."},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload.keys()),
            {"answer", "recommendations", "citations", "source", "fallback_used", "error_code", "provider"},
        )
        self.assertEqual(payload["recommendations"][0]["category_slug"], "smartphones")
        self.assertEqual(payload["recommendations"][0]["url"], "/customer/products/smartphones/42/")
        self.assertEqual(payload["citations"][0]["label"], "Behavior graph")

    def test_request_chatbot_reply_sanitizes_decimal_price_before_json_post(self):
        fake_response = type(
            "FakeResponse",
            (),
            {
                "ok": True,
                "content": b'{"answer":"ok","recommendations":[],"citations":[],"source":"chatbot_service"}',
                "json": staticmethod(lambda: {"answer": "ok", "recommendations": [], "citations": [], "source": "chatbot_service"}),
            },
        )()

        with patch("customer.services.requests.post", return_value=fake_response) as post_mock:
            request_chatbot_reply(
                question="Suggest a phone",
                current_product={
                    "category_slug": "smartphones",
                    "id": 42,
                    "name": "Pixel Frame 9",
                    "brand": "Google",
                    "price": Decimal("899.00"),
                },
                user_context={"cart_items": [], "saved_items": [], "recent_paid_items": []},
                user_ref="9",
                limit=4,
            )

        sent_json = post_mock.call_args.kwargs["json"]
        self.assertEqual(sent_json["current_product"]["price"], "899.00")

    def test_add_to_cart_serializes_decimal_unit_price_for_order_service(self):
        fake_response = type(
            "FakeResponse",
            (),
            {
                "ok": True,
                "status_code": 201,
                "content": b'{"item":{"id":1}}',
                "json": staticmethod(lambda: {"item": {"id": 1}}),
            },
        )()

        with patch("customer.services.requests.request", return_value=fake_response) as request_mock:
            add_to_cart(
                self.user.id,
                {
                    "category_slug": "smartphones",
                    "category_name": "Smartphones",
                    "product_id": 42,
                    "product_name": "Pixel Frame 9",
                    "product_brand": "Google",
                    "product_image_url": "https://example.com/pixel.jpg",
                    "unit_price": Decimal("899.00"),
                    "stock": 8,
                },
            )

        sent_json = request_mock.call_args.kwargs["json"]
        self.assertEqual(sent_json["unit_price"], "899.00")

    def test_dashboard_renders_ai_suggestion_block_for_search_results(self):
        categories = [
            {
                "id": 4,
                "slug": "smartphones",
                "name": "Smartphones",
                "description": "Phones for communication and capture.",
                "hero_image_url": "https://example.com/smartphones.jpg",
                "sort_order": 40,
            }
        ]
        products = [
            {
                "service": "smartphones",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "id": 42,
                "name": "Pixel Frame 9",
                "description": "Clean Android experience.",
                "image_url": "https://example.com/pixel.jpg",
                "brand": "Google",
                "price": "899.00",
                "stock": 8,
            }
        ]

        with patch("customer.views.fetch_categories", return_value=categories), patch(
            "customer.views.fetch_products",
            side_effect=lambda filters=None: list(products),
        ), patch(
            "customer.views.build_user_context_payload",
            return_value={"cart_items": [], "saved_items": [], "recent_paid_items": []},
        ), patch("customer.views.list_cart_items", return_value=[]), patch(
            "customer.views.list_saved_items",
            return_value=[],
        ), patch("customer.views.list_orders", return_value=[]), patch(
            "customer.views.build_dashboard_ai_suggestions",
            return_value={
                "summary": "AI selected this phone for the current search.",
                "recommendations": [
                    {
                        "service": "smartphones",
                        "category_slug": "smartphones",
                        "category_name": "Smartphones",
                        "id": 42,
                        "name": "Pixel Frame 9",
                        "brand": "Google",
                        "price": "899.00",
                        "stock": 8,
                        "image_url": "https://example.com/pixel.jpg",
                        "url": "/customer/products/smartphones/42/",
                    }
                ],
                "citations": [{"label": "Behavior graph", "url": "/customer/dashboard/"}],
                "source": "gemma_4_31b",
                "fallback_used": False,
                "provider": None,
                "empty_state": False,
            },
        ):
            response = self.client.get(reverse("customer_dashboard"), {"q": "pixel"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI goi y cho ban")
        self.assertContains(response, "AI selected this phone for the current search.")
        self.assertContains(response, "/customer/products/smartphones/42/")
        self.assertContains(response, "Behavior graph")

    def test_fetch_products_assigns_category_image_fallbacks(self):
        fake_response = type(
            "FakeResponse",
            (),
            {
                "ok": True,
                "content": b'[{"id":29,"name":"AirLite 13","brand":"ASUS","price":"999.00","stock":25,"category_slug":"ultrabooks","category_name":"Ultrabooks","image_url":"","description":"Thin ultrabook."}]',
                "json": staticmethod(
                    lambda: [
                        {
                            "id": 29,
                            "name": "AirLite 13",
                            "brand": "ASUS",
                            "price": "999.00",
                            "stock": 25,
                            "category_slug": "ultrabooks",
                            "category_name": "Ultrabooks",
                            "image_url": "",
                            "description": "Thin ultrabook.",
                        }
                    ]
                ),
            },
        )()

        with patch("customer.services.requests.request", return_value=fake_response):
            products = fetch_products({"category": "ultrabooks"})

        self.assertEqual(products[0]["category_slug"], "ultrabooks")
        self.assertEqual(products[0]["image_url"], "https://images.unsplash.com/photo-1496171367470-9ed9a91ea931?auto=format&fit=crop&w=1400&q=80")
        self.assertEqual(products[0]["image_fallback_url"], "https://images.unsplash.com/photo-1496171367470-9ed9a91ea931?auto=format&fit=crop&w=1400&q=80")

    def test_dashboard_renders_product_image_fallback_attributes(self):
        categories = [
            {
                "id": 3,
                "slug": "ultrabooks",
                "name": "Ultrabooks",
                "description": "Thin and light laptops.",
                "hero_image_url": "https://example.com/ultrabooks-hero.jpg",
                "sort_order": 30,
            }
        ]
        products = [
            {
                "service": "ultrabooks",
                "category_slug": "ultrabooks",
                "category_name": "Ultrabooks",
                "id": 29,
                "name": "AirLite 13",
                "description": "Thin ultrabook.",
                "image_url": "https://example.com/broken-airlite.jpg",
                "image_fallback_url": "https://example.com/ultrabooks-hero.jpg",
                "brand": "ASUS",
                "price": "999.00",
                "stock": 25,
            }
        ]

        with patch("customer.views.fetch_categories", return_value=categories), patch(
            "customer.views.fetch_products",
            side_effect=lambda filters=None: list(products),
        ), patch("customer.views.list_saved_items", return_value=[]), patch(
            "customer.views.list_cart_items",
            return_value=[],
        ), patch("customer.views.list_orders", return_value=[]), patch(
            "customer.views.build_user_context_payload",
            return_value={"cart_items": [], "saved_items": [], "recent_paid_items": []},
        ), patch(
            "customer.views.build_dashboard_ai_suggestions",
            return_value=None,
        ):
            response = self.client.get(reverse("customer_dashboard"), {"category": "ultrabooks"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fallback-src="https://example.com/ultrabooks-hero.jpg"', html=False)
        self.assertContains(response, "this.dataset.fallbackSrc", html=False)

    def test_cart_renders_recommendations_and_keeps_chat_widget(self):
        cart_items = [
            {
                "id": 1,
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "product_service": "smartphones",
                "product_id": 42,
                "product_name": "Pixel Frame 9",
                "product_brand": "Google",
                "product_image_url": "https://example.com/pixel.jpg",
                "quantity": 1,
                "total_price": "899.00",
            }
        ]
        recommendations = {
            "summary": "These add-on products complement the categories already in your cart.",
            "recommendations": [
                {
                    "service": "audio",
                    "category_slug": "audio",
                    "category_name": "Audio",
                    "id": 84,
                    "name": "Studio Monitor One",
                    "brand": "Audio-Technica",
                    "price": "179.00",
                    "stock": 11,
                    "image_url": "https://example.com/audio.jpg",
                    "url": "/customer/products/audio/84/",
                }
            ],
            "citations": [],
            "source": "cart_local_fallback",
            "fallback_used": True,
            "provider": None,
            "empty_state": False,
        }

        with patch("customer.views.fetch_categories", return_value=[]), patch(
            "customer.views.list_cart_items",
            return_value=cart_items,
        ), patch(
            "customer.views.build_cart_ai_suggestions",
            return_value=recommendations,
        ):
            response = self.client.get(reverse("customer_cart"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add More To")
        self.assertContains(response, "These add-on products complement the categories already in your cart.")
        self.assertContains(response, "/customer/products/audio/84/")
        self.assertContains(response, 'id="cart-rec-add-84"', html=False)
        self.assertContains(response, 'data-chat-endpoint="/customer/chatbot/reply/"', html=False)


class CustomerOrderPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="buyer",
            email="buyer@example.com",
            password="pass12345",
        )
        self.client.force_login(self.user)

    def test_paid_order_labels_payment_and_shipping_statuses_separately(self):
        orders = [
            {
                "id": 139,
                "created_at": "2026-04-27T17:41:59+07:00",
                "payment_status": "paid",
                "shipping_status": "pending",
                "total_amount": "188.00",
                "shipping": {
                    "recipient_name": "hoang",
                    "phone": "0964768205",
                    "address_line": "la thanh",
                    "city_or_region": "ha noi",
                    "postal_code": "100000",
                    "country": "VN",
                },
                "items": [
                    {
                        "product_name": "Tablet Rest Pro",
                        "category_name": "Bags & Stands",
                        "category_slug": "bags-stands",
                        "product_service": "bags-stands",
                        "product_brand": "MOFT",
                        "quantity": 1,
                        "unit_price": "59.00",
                    }
                ],
            }
        ]

        with patch("customer.views.fetch_categories", return_value=[]), patch(
            "customer.views.list_orders",
            return_value=orders,
        ):
            response = self.client.get(reverse("customer_orders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment")
        self.assertContains(response, "Complete")
        self.assertContains(response, "Shipping")
        self.assertContains(response, "Pending")
        self.assertNotContains(response, "Pay Now")
