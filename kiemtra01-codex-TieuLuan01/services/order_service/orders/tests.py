import json
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .management.commands import import_legacy_orders as import_legacy_orders_command
from .models import CartItem, Order, OrderItem, OrderShipping
from .service_clients import DownstreamServiceError
from .views import _build_customer_analytics


class _FakeCursor:
    def __init__(self, responses):
        self.responses = responses
        self.current = []

    def execute(self, sql):
        normalized = " ".join(str(sql).split())
        for pattern, rows in self.responses.items():
            if pattern in normalized:
                self.current = rows
                return
        raise AssertionError(f"Unexpected SQL executed: {normalized}")

    def fetchall(self):
        return list(self.current)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self, responses):
        self.responses = responses

    def cursor(self):
        return _FakeCursor(self.responses)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class OrderServiceTests(TestCase):
    def setUp(self):
        self.client.defaults["HTTP_X_INTERNAL_KEY"] = "dev-order-internal-key"
        self.payment_create_patcher = patch("orders.views.create_pending_payment", side_effect=self._fake_create_payment)
        self.payment_confirm_patcher = patch("orders.views.confirm_order_payment", side_effect=self._fake_confirm_payment)
        self.shipment_create_patcher = patch("orders.views.create_pending_shipment", side_effect=self._fake_create_shipment)
        self.shipment_update_patcher = patch("orders.views.update_order_shipment_status", side_effect=self._fake_update_shipment)
        self.create_payment_mock = self.payment_create_patcher.start()
        self.confirm_payment_mock = self.payment_confirm_patcher.start()
        self.create_shipment_mock = self.shipment_create_patcher.start()
        self.update_shipment_mock = self.shipment_update_patcher.start()
        self.addCleanup(self.payment_create_patcher.stop)
        self.addCleanup(self.payment_confirm_patcher.stop)
        self.addCleanup(self.shipment_create_patcher.stop)
        self.addCleanup(self.shipment_update_patcher.stop)

    def _fake_create_payment(self, order):
        return {
            "id": order.id + 1000,
            "order_id": order.id,
            "user_id": order.user_id,
            "amount": f"{order.total_amount:.2f}",
            "status": "pending",
        }

    def _fake_confirm_payment(self, order):
        return {
            "id": order.id + 1000,
            "order_id": order.id,
            "user_id": order.user_id,
            "amount": f"{order.total_amount:.2f}",
            "status": "paid",
            "paid_at": timezone.now().isoformat(),
        }

    def _fake_create_shipment(self, order, shipping_data):
        return {
            "id": order.id + 2000,
            "order_id": order.id,
            "user_id": order.user_id,
            **shipping_data,
            "status": "pending",
        }

    def _fake_update_shipment(self, order, shipping_status, shipping_data=None):
        return {
            "id": order.id + 2000,
            "order_id": order.id,
            "user_id": order.user_id,
            "status": shipping_status,
        }

    def _item_payload(self, **overrides):
        payload = {
            "user_id": 7,
            "category_slug": "smartphones",
            "category_name": "Smartphones",
            "product_id": 101,
            "product_name": "SkyPhone X",
            "product_brand": "Apple",
            "product_image_url": "https://example.com/skyphone.jpg",
            "unit_price": "1099.00",
            "quantity": 1,
            "stock": 9,
        }
        payload.update(overrides)
        return payload

    def _shipping_payload(self, **overrides):
        payload = {
            "user_id": 7,
            "recipient_name": "Nguyen Van A",
            "phone": "0123456789",
            "address_line": "123 Example Street",
            "city_or_region": "Ho Chi Minh City",
            "postal_code": "700000",
            "country": "VN",
            "note": "Call before delivery",
        }
        payload.update(overrides)
        return payload

    def _checkout_order(self, **item_overrides):
        self.client.post(
            "/api/cart/",
            data=json.dumps(self._item_payload(**item_overrides)),
            content_type="application/json",
        )
        response = self.client.post(
            "/api/checkout/",
            data=json.dumps(self._shipping_payload(user_id=item_overrides.get("user_id", 7))),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["order"]

    def test_order_api_requires_internal_key(self):
        client = self.client_class()
        response = client.get("/api/cart/?user_id=7")
        self.assertEqual(response.status_code, 403)

    def test_cart_checkout_pay_and_staff_shipping_flow(self):
        add_response = self.client.post(
            "/api/cart/",
            data=json.dumps(self._item_payload()),
            content_type="application/json",
        )
        self.assertEqual(add_response.status_code, 201)

        checkout_response = self.client.post(
            "/api/checkout/",
            data=json.dumps(self._shipping_payload()),
            content_type="application/json",
        )
        self.assertEqual(checkout_response.status_code, 201)
        order = checkout_response.json()["order"]
        self.assertEqual(order["payment_status"], Order.PAYMENT_PENDING)
        self.assertEqual(order["shipping_status"], Order.SHIPPING_PENDING)
        self.assertEqual(order["shipping"]["recipient_name"], "Nguyen Van A")
        self.assertEqual(len(order["items"]), 1)
        self.create_payment_mock.assert_called_once()
        self.create_shipment_mock.assert_called_once()

        pay_response = self.client.post(
            f"/api/orders/{order['id']}/pay/",
            data=json.dumps({"user_id": 7}),
            content_type="application/json",
        )
        self.assertEqual(pay_response.status_code, 200)
        self.assertEqual(pay_response.json()["order"]["payment_status"], Order.PAYMENT_PAID)
        self.confirm_payment_mock.assert_called_once()

        shipping_response = self.client.post(
            f"/api/staff/orders/{order['id']}/shipping/",
            data=json.dumps({"shipping_status": Order.SHIPPING_PREPARING}),
            content_type="application/json",
        )
        self.assertEqual(shipping_response.status_code, 200)
        self.assertEqual(shipping_response.json()["order"]["shipping_status"], Order.SHIPPING_PREPARING)
        self.update_shipment_mock.assert_called_once()
        self.assertEqual(CartItem.objects.count(), 0)

    def test_checkout_rolls_back_when_payment_service_fails(self):
        self.create_payment_mock.side_effect = DownstreamServiceError("Payment service unavailable.", status_code=503)
        add_response = self.client.post(
            "/api/cart/",
            data=json.dumps(self._item_payload(product_id=333, product_name="Rollback Item")),
            content_type="application/json",
        )
        self.assertEqual(add_response.status_code, 201)

        checkout_response = self.client.post(
            "/api/checkout/",
            data=json.dumps(self._shipping_payload()),
            content_type="application/json",
        )

        self.assertEqual(checkout_response.status_code, 502)
        self.assertEqual(checkout_response.json()["error"], "Payment service unavailable.")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(CartItem.objects.count(), 1)

    def test_compare_is_limited_to_four_items(self):
        for product_id in range(1, 5):
            response = self.client.post(
                "/api/compare/toggle/",
                data=json.dumps(self._item_payload(product_id=product_id, product_name=f"Item {product_id}")),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 201)

        overflow = self.client.post(
            "/api/compare/toggle/",
            data=json.dumps(self._item_payload(product_id=999, product_name="Overflow")),
            content_type="application/json",
        )
        self.assertEqual(overflow.status_code, 400)

    def test_internal_post_endpoints_do_not_require_browser_csrf_tokens(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.defaults["HTTP_X_INTERNAL_KEY"] = "dev-order-internal-key"

        cart_response = client.post(
            "/api/cart/",
            data=json.dumps(self._item_payload(product_id=201, product_name="Cart Item")),
            content_type="application/json",
        )
        self.assertEqual(cart_response.status_code, 201)

        saved_response = client.post(
            "/api/saved/toggle/",
            data=json.dumps(self._item_payload(product_id=202, product_name="Saved Item")),
            content_type="application/json",
        )
        self.assertEqual(saved_response.status_code, 201)
        self.assertEqual(saved_response.json()["action"], "saved")

        compare_response = client.post(
            "/api/compare/toggle/",
            data=json.dumps(self._item_payload(product_id=203, product_name="Compare Item")),
            content_type="application/json",
        )
        self.assertEqual(compare_response.status_code, 201)
        self.assertEqual(compare_response.json()["action"], "added")

    def test_staff_shipping_requires_paid_order_and_customer_can_view_each_phase(self):
        order = self._checkout_order()

        unpaid_response = self.client.post(
            f"/api/staff/orders/{order['id']}/shipping/",
            data=json.dumps({"shipping_status": Order.SHIPPING_SHIPPED}),
            content_type="application/json",
        )
        self.assertEqual(unpaid_response.status_code, 400)
        self.assertEqual(unpaid_response.json()["error"], "Only paid orders can advance shipping.")

        self.client.post(
            f"/api/orders/{order['id']}/pay/",
            data=json.dumps({"user_id": 7}),
            content_type="application/json",
        )

        preparing_response = self.client.post(
            f"/api/staff/orders/{order['id']}/shipping/",
            data=json.dumps({"shipping_status": Order.SHIPPING_PREPARING}),
            content_type="application/json",
        )
        self.assertEqual(preparing_response.status_code, 200)
        customer_preparing = self.client.get("/api/orders/?user_id=7")
        self.assertEqual(customer_preparing.status_code, 200)
        self.assertEqual(customer_preparing.json()["orders"][0]["shipping_status"], Order.SHIPPING_PREPARING)

        shipped_response = self.client.post(
            f"/api/staff/orders/{order['id']}/shipping/",
            data=json.dumps({"shipping_status": Order.SHIPPING_SHIPPED}),
            content_type="application/json",
        )
        self.assertEqual(shipped_response.status_code, 200)
        customer_shipped = self.client.get("/api/orders/?user_id=7")
        self.assertEqual(customer_shipped.status_code, 200)
        self.assertEqual(customer_shipped.json()["orders"][0]["shipping_status"], Order.SHIPPING_SHIPPED)

        delivered_response = self.client.post(
            f"/api/staff/orders/{order['id']}/shipping/",
            data=json.dumps({"shipping_status": Order.SHIPPING_DELIVERED}),
            content_type="application/json",
        )
        self.assertEqual(delivered_response.status_code, 200)
        customer_delivered = self.client.get("/api/orders/?user_id=7")
        self.assertEqual(customer_delivered.status_code, 200)
        self.assertEqual(customer_delivered.json()["orders"][0]["shipping_status"], Order.SHIPPING_DELIVERED)

    def test_cancelled_shipping_order_cannot_be_paid(self):
        order = self._checkout_order()

        cancel_response = self.client.post(
            f"/api/staff/orders/{order['id']}/shipping/",
            data=json.dumps({"shipping_status": Order.SHIPPING_CANCELLED}),
            content_type="application/json",
        )
        self.assertEqual(cancel_response.status_code, 200)

        pay_response = self.client.post(
            f"/api/orders/{order['id']}/pay/",
            data=json.dumps({"user_id": 7}),
            content_type="application/json",
        )
        self.assertEqual(pay_response.status_code, 400)
        self.assertEqual(pay_response.json()["error"], "Cancelled shipments cannot be paid.")

    def test_customer_analytics_groups_rows_by_user_id(self):
        self.client.post(
            "/api/cart/",
            data=json.dumps(self._item_payload(user_id=1, product_id=11, product_name="Alpha")),
            content_type="application/json",
        )
        checkout_response = self.client.post(
            "/api/checkout/",
            data=json.dumps(self._shipping_payload(user_id=1, recipient_name="A", phone="1", address_line="Street 1", city_or_region="HCMC", note="")),
            content_type="application/json",
        )
        self.assertEqual(checkout_response.status_code, 201)
        order_id = checkout_response.json()["order"]["id"]

        pay_response = self.client.post(
            f"/api/orders/{order_id}/pay/",
            data=json.dumps({"user_id": 1}),
            content_type="application/json",
        )
        self.assertEqual(pay_response.status_code, 200)

        analytics_response = self.client.get("/api/analytics/customers/?range_days=30")
        self.assertEqual(analytics_response.status_code, 200)
        payload = analytics_response.json()
        self.assertEqual(payload["order_stats"]["paid_orders"], 1)
        self.assertEqual(payload["customer_rows"][0]["user_id"], 1)

    def test_customer_analytics_active_customer_count_is_not_trimmed_by_limit(self):
        now = timezone.now()
        for user_id in (1, 2, 3):
            order = Order.objects.create(
                user_id=user_id,
                total_amount="99.00",
                payment_status=Order.PAYMENT_PAID,
                shipping_status=Order.SHIPPING_DELIVERED,
                paid_at=now,
            )
            OrderShipping.objects.create(
                order=order,
                recipient_name=f"User {user_id}",
                phone="1",
                address_line="Street",
                city_or_region="HCMC",
                postal_code="700000",
                country="VN",
                note="",
            )
            OrderItem.objects.create(
                order=order,
                category_slug="smartphones",
                category_name="Smartphones",
                product_id=100 + user_id,
                product_name=f"Phone {user_id}",
                product_brand="Brand",
                product_image_url="",
                unit_price="99.00",
                quantity=1,
            )

        payload = _build_customer_analytics(customer_limit=1, recent_limit=5, range_days=30)
        self.assertEqual(payload["customer_count"], 3)
        self.assertEqual(payload["active_customers"], 3)
        self.assertEqual(len(payload["customer_rows"]), 1)

    def test_order_list_handles_missing_shipping_snapshot(self):
        order = Order.objects.create(
            user_id=9,
            total_amount="49.00",
            payment_status=Order.PAYMENT_PENDING,
            shipping_status=Order.SHIPPING_PENDING,
        )
        OrderItem.objects.create(
            order=order,
            category_slug="accessories",
            category_name="Accessories",
            product_id=501,
            product_name="Mouse",
            product_brand="Brand",
            product_image_url="",
            unit_price="49.00",
            quantity=1,
        )

        response = self.client.get("/api/orders/?user_id=9")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["orders"][0]["shipping"])

    def test_import_legacy_orders_uses_mapping_preserves_snapshot_and_is_idempotent(self):
        legacy_created_at = timezone.now() - timedelta(days=5)
        mapping_rows = [
            {"legacy_source": "customer", "legacy_user_id": 15, "user_id": 201},
        ]
        legacy_orders = [
            {
                "id": 301,
                "user_id": 15,
                "total_amount": "1499.00",
                "status": "paid",
                "created_at": legacy_created_at,
            }
        ]
        legacy_items = [
            {
                "id": 1,
                "order_id": 301,
                "product_service": "laptops",
                "product_id": 88,
                "product_name": "Legacy Laptop",
                "product_brand": "Dell",
                "unit_price": "1499.00",
                "quantity": 1,
            }
        ]

        def fake_mysql_connection(database_name):
            if database_name == "user_db":
                return _FakeConnection(
                    {"FROM customer_legacyusermapping": mapping_rows}
                )
            if database_name == "legacy_db":
                return _FakeConnection(
                    {
                        "FROM customer_order ORDER BY id ASC": legacy_orders,
                        "FROM customer_orderitem ORDER BY id ASC": legacy_items,
                    }
                )
            raise AssertionError(f"Unexpected database requested: {database_name}")

        with patch.object(import_legacy_orders_command, "_mysql_connection", side_effect=fake_mysql_connection):
            call_command("import_legacy_orders", legacy_db="legacy_db", user_db="user_db")
            call_command("import_legacy_orders", legacy_db="legacy_db", user_db="user_db")

        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get(source=Order.SOURCE_LEGACY_IMPORT, source_order_id=301)
        self.assertEqual(order.user_id, 201)
        self.assertEqual(order.payment_status, Order.PAYMENT_PAID)
        self.assertEqual(order.shipping_status, Order.SHIPPING_PENDING)
        self.assertEqual(order.created_at, legacy_created_at)
        self.assertEqual(order.updated_at, legacy_created_at)
        self.assertEqual(order.paid_at, legacy_created_at)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().product_name, "Legacy Laptop")
        self.assertEqual(order.shipping.note, "Imported from legacy customer_db without shipping snapshot.")
