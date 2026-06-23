from django.test import TestCase
from rest_framework.test import APIClient

from .models import Payment
from .permissions import expected_internal_key


class PaymentServiceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_INTERNAL_KEY=expected_internal_key())

    def _payload(self, **overrides):
        payload = {
            "order_id": 101,
            "user_id": 7,
            "amount": "149.99",
        }
        payload.update(overrides)
        return payload

    def test_payment_api_requires_internal_key(self):
        client = APIClient()
        response = client.post("/api/payments/", self._payload(), format="json")
        self.assertEqual(response.status_code, 403)

    def test_create_retrieve_and_lookup_by_order(self):
        create_response = self.client.post("/api/payments/", self._payload(), format="json")
        self.assertEqual(create_response.status_code, 201)
        payload = create_response.json()
        self.assertEqual(payload["order_id"], 101)
        self.assertEqual(payload["user_id"], 7)
        self.assertEqual(payload["amount"], "149.99")
        self.assertEqual(payload["status"], Payment.STATUS_PENDING)
        self.assertIsNone(payload["paid_at"])

        detail_response = self.client.get(f"/api/payments/{payload['id']}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["id"], payload["id"])

        by_order_response = self.client.get("/api/payments/by-order/101/")
        self.assertEqual(by_order_response.status_code, 200)
        self.assertEqual(by_order_response.json()["id"], payload["id"])

    def test_payment_confirm_lifecycle(self):
        create_response = self.client.post("/api/payments/", self._payload(order_id=202), format="json")
        payment_id = create_response.json()["id"]

        confirm_response = self.client.post(f"/api/payments/{payment_id}/confirm/")
        self.assertEqual(confirm_response.status_code, 200)
        payload = confirm_response.json()
        self.assertEqual(payload["status"], Payment.STATUS_PAID)
        self.assertIsNotNone(payload["paid_at"])

        second_confirm = self.client.post(f"/api/payments/{payment_id}/confirm/")
        self.assertEqual(second_confirm.status_code, 400)
        self.assertEqual(second_confirm.json()["error"], "Only pending payments can be confirmed.")

        cancel_paid = self.client.post(f"/api/payments/{payment_id}/cancel/")
        self.assertEqual(cancel_paid.status_code, 400)
        self.assertEqual(cancel_paid.json()["error"], "Only pending payments can be cancelled.")

    def test_payment_cancel_lifecycle(self):
        create_response = self.client.post("/api/payments/", self._payload(order_id=303), format="json")
        payment_id = create_response.json()["id"]

        cancel_response = self.client.post(f"/api/payments/{payment_id}/cancel/")
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["status"], Payment.STATUS_CANCELLED)
        self.assertIsNone(cancel_response.json()["paid_at"])

        confirm_cancelled = self.client.post(f"/api/payments/{payment_id}/confirm/")
        self.assertEqual(confirm_cancelled.status_code, 400)
        self.assertEqual(confirm_cancelled.json()["error"], "Only pending payments can be confirmed.")

    def test_create_validates_amount_status_and_order_uniqueness(self):
        invalid_amount = self.client.post(
            "/api/payments/",
            self._payload(order_id=401, amount="0.00"),
            format="json",
        )
        self.assertEqual(invalid_amount.status_code, 400)

        invalid_status = self.client.post(
            "/api/payments/",
            self._payload(order_id=402, status=Payment.STATUS_PAID),
            format="json",
        )
        self.assertEqual(invalid_status.status_code, 400)

        created = self.client.post("/api/payments/", self._payload(order_id=403), format="json")
        self.assertEqual(created.status_code, 201)
        duplicate = self.client.post("/api/payments/", self._payload(order_id=403), format="json")
        self.assertEqual(duplicate.status_code, 400)
