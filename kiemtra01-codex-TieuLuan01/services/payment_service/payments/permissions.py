import hmac
import os

from rest_framework.permissions import BasePermission


def expected_internal_key():
    return str(
        os.getenv("PAYMENT_SERVICE_INTERNAL_KEY")
        or os.getenv("ORDER_SERVICE_INTERNAL_KEY")
        or os.getenv("STAFF_API_KEY")
        or "dev-payment-internal-key"
    ).strip()


class InternalKeyPermission(BasePermission):
    def has_permission(self, request, view):
        provided_key = str(
            request.headers.get("X-Internal-Key")
            or request.headers.get("X-Service-Key")
            or ""
        ).strip()
        expected_key = expected_internal_key()
        return bool(provided_key and expected_key and hmac.compare_digest(provided_key, expected_key))
