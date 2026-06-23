import os
from decimal import Decimal

import requests


class DownstreamServiceError(Exception):
    def __init__(self, message, *, status_code=503, data=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.data = data or {}


def _service_url(env_name, default):
    return (os.getenv(env_name) or default).rstrip("/")


def _internal_key(service_env_name):
    return str(
        os.getenv(service_env_name)
        or os.getenv("ORDER_SERVICE_INTERNAL_KEY")
        or os.getenv("STAFF_API_KEY")
        or "dev-order-internal-key"
    ).strip()


def _payment_service_url():
    return _service_url("PAYMENT_SERVICE_URL", "http://payment-service:8000")


def _shipping_service_url():
    return _service_url("SHIPPING_SERVICE_URL", "http://shipping-service:8000")


def _json_ready(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _message_from_data(data, default):
    if not isinstance(data, dict):
        return default
    value = data.get("error") or data.get("detail")
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if value:
        return str(value)
    for field, errors in data.items():
        if isinstance(errors, list) and errors:
            return f"{field}: {errors[0]}"
        if errors:
            return f"{field}: {errors}"
    return default


def _request_json(method, url, *, payload=None, headers=None, timeout=8, default_error="upstream_error"):
    try:
        response = requests.request(
            method=method,
            url=url,
            json=_json_ready(payload),
            headers=headers,
            timeout=timeout,
        )
        data = response.json() if response.content else {}
    except ValueError as exc:
        raise DownstreamServiceError("Invalid response from downstream service.", status_code=502) from exc
    except requests.RequestException as exc:
        raise DownstreamServiceError("Downstream service is unavailable.", status_code=503) from exc

    if response.ok:
        return data if isinstance(data, dict) else {"results": data}
    raise DownstreamServiceError(
        _message_from_data(data, default_error),
        status_code=response.status_code,
        data=data if isinstance(data, dict) else {},
    )


def _payment_headers():
    return {"X-Internal-Key": _internal_key("PAYMENT_SERVICE_INTERNAL_KEY")}


def _shipping_headers():
    return {"X-Internal-Key": _internal_key("SHIPPING_SERVICE_INTERNAL_KEY")}


def _downstream_error_status(exc):
    if exc.status_code in {400, 403, 404, 409}:
        return exc.status_code
    return 502


def error_response_status(exc):
    return _downstream_error_status(exc)


def get_payment_by_order(order_id):
    try:
        return _request_json(
            "GET",
            f"{_payment_service_url()}/api/payments/by-order/{order_id}/",
            headers=_payment_headers(),
            default_error="Payment lookup failed.",
        )
    except DownstreamServiceError as exc:
        if exc.status_code == 404:
            return None
        raise


def create_pending_payment(order):
    return _request_json(
        "POST",
        f"{_payment_service_url()}/api/payments/",
        payload={
            "order_id": order.id,
            "user_id": order.user_id,
            "amount": order.total_amount,
            "status": "pending",
        },
        headers=_payment_headers(),
        default_error="Payment could not be created.",
    )


def cancel_payment(payment):
    payment_id = (payment or {}).get("id")
    if not payment_id:
        return None
    try:
        return _request_json(
            "POST",
            f"{_payment_service_url()}/api/payments/{payment_id}/cancel/",
            headers=_payment_headers(),
            default_error="Payment could not be cancelled.",
        )
    except DownstreamServiceError:
        return None


def confirm_order_payment(order):
    payment = get_payment_by_order(order.id)
    if payment is None:
        payment = create_pending_payment(order)

    status = str(payment.get("status") or "").strip().lower()
    if status == "paid":
        return payment
    if status != "pending":
        raise DownstreamServiceError(f"Payment is {status or 'unavailable'} and cannot be confirmed.", status_code=400)

    return _request_json(
        "POST",
        f"{_payment_service_url()}/api/payments/{payment['id']}/confirm/",
        headers=_payment_headers(),
        default_error="Payment could not be confirmed.",
    )


def get_shipment_by_order(order_id):
    try:
        return _request_json(
            "GET",
            f"{_shipping_service_url()}/api/shipments/by-order/{order_id}/",
            headers=_shipping_headers(),
            default_error="Shipment lookup failed.",
        )
    except DownstreamServiceError as exc:
        if exc.status_code == 404:
            return None
        raise


def create_pending_shipment(order, shipping_data):
    return _request_json(
        "POST",
        f"{_shipping_service_url()}/api/shipments/",
        payload={
            "order_id": order.id,
            "user_id": order.user_id,
            **shipping_data,
            "status": "pending",
        },
        headers=_shipping_headers(),
        default_error="Shipment could not be created.",
    )


def update_order_shipment_status(order, shipping_status, shipping_data=None):
    shipment = get_shipment_by_order(order.id)
    if shipment is None:
        if order.shipping_status != "pending" or not shipping_data:
            raise DownstreamServiceError("Shipment record is missing for this order.", status_code=404)
        shipment = create_pending_shipment(order, shipping_data)

    return _request_json(
        "POST",
        f"{_shipping_service_url()}/api/shipments/{shipment['id']}/status/",
        payload={"shipping_status": shipping_status},
        headers=_shipping_headers(),
        default_error="Shipment status could not be updated.",
    )
