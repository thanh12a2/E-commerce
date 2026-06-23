from django.test import TestCase
from rest_framework.test import APIClient

from .models import Shipment
from .permissions import expected_internal_key


class ShippingServiceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_INTERNAL_KEY=expected_internal_key())

    def _payload(self, **overrides):
        payload = {
            "order_id": 101,
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

    def test_shipment_api_requires_internal_key(self):
        client = APIClient()
        response = client.post("/api/shipments/", self._payload(), format="json")
        self.assertEqual(response.status_code, 403)

    def test_create_retrieve_and_lookup_by_order(self):
        create_response = self.client.post("/api/shipments/", self._payload(), format="json")
        self.assertEqual(create_response.status_code, 201)
        payload = create_response.json()
        self.assertEqual(payload["order_id"], 101)
        self.assertEqual(payload["user_id"], 7)
        self.assertEqual(payload["recipient_name"], "Nguyen Van A")
        self.assertEqual(payload["status"], Shipment.STATUS_PENDING)

        detail_response = self.client.get(f"/api/shipments/{payload['id']}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["id"], payload["id"])

        by_order_response = self.client.get("/api/shipments/by-order/101/")
        self.assertEqual(by_order_response.status_code, 200)
        self.assertEqual(by_order_response.json()["id"], payload["id"])

    def test_create_validates_status_and_order_uniqueness(self):
        invalid_status = self.client.post(
            "/api/shipments/",
            self._payload(order_id=201, status=Shipment.STATUS_SHIPPED),
            format="json",
        )
        self.assertEqual(invalid_status.status_code, 400)

        created = self.client.post("/api/shipments/", self._payload(order_id=202), format="json")
        self.assertEqual(created.status_code, 201)
        duplicate = self.client.post("/api/shipments/", self._payload(order_id=202), format="json")
        self.assertEqual(duplicate.status_code, 400)

    def test_shipment_status_lifecycle_accepts_patch_and_post(self):
        create_response = self.client.post("/api/shipments/", self._payload(order_id=303), format="json")
        shipment_id = create_response.json()["id"]

        preparing_response = self.client.patch(
            f"/api/shipments/{shipment_id}/status/",
            {"status": Shipment.STATUS_PREPARING},
            format="json",
        )
        self.assertEqual(preparing_response.status_code, 200)
        self.assertEqual(preparing_response.json()["status"], Shipment.STATUS_PREPARING)

        shipped_response = self.client.post(
            f"/api/shipments/{shipment_id}/status/",
            {"shipping_status": Shipment.STATUS_SHIPPED},
            format="json",
        )
        self.assertEqual(shipped_response.status_code, 200)
        self.assertEqual(shipped_response.json()["status"], Shipment.STATUS_SHIPPED)

        delivered_response = self.client.patch(
            f"/api/shipments/{shipment_id}/status/",
            {"status": Shipment.STATUS_DELIVERED},
            format="json",
        )
        self.assertEqual(delivered_response.status_code, 200)
        self.assertEqual(delivered_response.json()["status"], Shipment.STATUS_DELIVERED)

    def test_shipment_accepts_forward_status_jumps(self):
        create_response = self.client.post("/api/shipments/", self._payload(order_id=404), format="json")
        shipment_id = create_response.json()["id"]

        delivered_response = self.client.patch(
            f"/api/shipments/{shipment_id}/status/",
            {"status": Shipment.STATUS_DELIVERED},
            format="json",
        )
        self.assertEqual(delivered_response.status_code, 200)
        self.assertEqual(delivered_response.json()["status"], Shipment.STATUS_DELIVERED)

        shipped_response = self.client.patch(
            f"/api/shipments/{shipment_id}/status/",
            {"status": Shipment.STATUS_SHIPPED},
            format="json",
        )
        self.assertEqual(shipped_response.status_code, 400)
        self.assertEqual(
            shipped_response.json()["error"],
            "Cannot move shipment from delivered to shipped.",
        )

    def test_cancelled_shipment_is_terminal(self):
        create_response = self.client.post("/api/shipments/", self._payload(order_id=505), format="json")
        shipment_id = create_response.json()["id"]

        cancel_response = self.client.post(
            f"/api/shipments/{shipment_id}/status/",
            {"status": Shipment.STATUS_CANCELLED},
            format="json",
        )
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["status"], Shipment.STATUS_CANCELLED)

        preparing_response = self.client.post(
            f"/api/shipments/{shipment_id}/status/",
            {"status": Shipment.STATUS_PREPARING},
            format="json",
        )
        self.assertEqual(preparing_response.status_code, 400)
        self.assertEqual(
            preparing_response.json()["error"],
            "Cannot move shipment from cancelled to preparing.",
        )
