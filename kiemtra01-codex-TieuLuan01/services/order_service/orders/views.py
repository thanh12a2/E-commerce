import hmac
import json
import os
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .models import CartItem, CompareItem, Order, OrderItem, OrderShipping, SavedItem
from .service_clients import (
    DownstreamServiceError,
    cancel_payment,
    confirm_order_payment,
    create_pending_payment,
    create_pending_shipment,
    error_response_status,
    update_order_shipment_status,
)


def _json_error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _expected_internal_key():
    return str(
        os.getenv("ORDER_SERVICE_INTERNAL_KEY")
        or os.getenv("STAFF_API_KEY")
        or "dev-order-internal-key"
    ).strip()


def _require_internal_access(request):
    provided_key = str(
        request.headers.get("X-Internal-Key")
        or request.headers.get("X-Service-Key")
        or ""
    ).strip()
    expected_key = _expected_internal_key()
    if provided_key and expected_key and hmac.compare_digest(provided_key, expected_key):
        return None
    return _json_error("Forbidden", status=403)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_decimal(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return default


def _parse_request_payload(request):
    if "application/json" in (request.content_type or "").lower():
        try:
            return json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    return request.POST.dict()


def _resolve_user_id(request, payload=None):
    payload = payload or {}
    return _safe_int(
        payload.get("user_id")
        or request.GET.get("user_id")
        or request.headers.get("X-User-Id"),
        0,
    )


def _decimal_str(value):
    return f"{_safe_decimal(value):.2f}"


def _format_datetime(value):
    if value is None:
        return None
    return timezone.localtime(value).isoformat()


def _category_payload(category_slug, category_name):
    slug = str(category_slug or "").strip().lower()
    return {
        "category_slug": slug,
        "category_name": str(category_name or "").strip(),
        "product_service": slug,
    }


def _serialize_cart_item(item):
    payload = _category_payload(item.category_slug, item.category_name)
    payload.update(
        {
            "id": item.id,
            "user_id": item.user_id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "product_brand": item.product_brand,
            "product_image_url": item.product_image_url,
            "unit_price": _decimal_str(item.unit_price),
            "quantity": item.quantity,
            "total_price": _decimal_str(item.total_price),
            "created_at": _format_datetime(item.created_at),
            "updated_at": _format_datetime(item.updated_at),
        }
    )
    return payload


def _serialize_saved_item(item):
    payload = _category_payload(item.category_slug, item.category_name)
    payload.update(
        {
            "id": item.id,
            "user_id": item.user_id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "product_brand": item.product_brand,
            "product_image_url": item.product_image_url,
            "unit_price": _decimal_str(item.unit_price),
            "created_at": _format_datetime(item.created_at),
        }
    )
    return payload


def _serialize_compare_item(item):
    payload = _category_payload(item.category_slug, item.category_name)
    payload.update(
        {
            "id": item.id,
            "user_id": item.user_id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "product_brand": item.product_brand,
            "product_image_url": item.product_image_url,
            "unit_price": _decimal_str(item.unit_price),
            "stock": item.stock,
            "created_at": _format_datetime(item.created_at),
        }
    )
    return payload


def _serialize_order_item(item):
    payload = _category_payload(item.category_slug, item.category_name)
    payload.update(
        {
            "id": item.id,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "product_brand": item.product_brand,
            "product_image_url": item.product_image_url,
            "unit_price": _decimal_str(item.unit_price),
            "quantity": item.quantity,
            "total_price": _decimal_str(item.total_price),
        }
    )
    return payload


def _serialize_shipping(shipping):
    if shipping is None:
        return None
    return {
        "recipient_name": shipping.recipient_name,
        "phone": shipping.phone,
        "address_line": shipping.address_line,
        "city_or_region": shipping.city_or_region,
        "postal_code": shipping.postal_code,
        "country": shipping.country,
        "note": shipping.note,
    }


def _order_shipping_payload(order):
    try:
        shipping = order.shipping
    except OrderShipping.DoesNotExist:
        return None
    return _serialize_shipping(shipping)


def _serialize_order(order):
    try:
        shipping = order.shipping
    except OrderShipping.DoesNotExist:
        shipping = None
    return {
        "id": order.id,
        "user_id": order.user_id,
        "total_amount": _decimal_str(order.total_amount),
        "payment_status": order.payment_status,
        "shipping_status": order.shipping_status,
        "source": order.source,
        "status": order.payment_status,
        "created_at": _format_datetime(order.created_at),
        "updated_at": _format_datetime(order.updated_at),
        "paid_at": _format_datetime(order.paid_at),
        "shipping": _serialize_shipping(shipping),
        "items": [_serialize_order_item(item) for item in order.items.all()],
    }


def _build_item_payload(payload):
    category_slug = str(payload.get("category_slug") or payload.get("product_service") or "").strip().lower()
    product_id = _safe_int(payload.get("product_id"), 0)
    unit_price = max(_safe_decimal(payload.get("unit_price"), Decimal("0")), Decimal("0"))
    quantity = max(1, _safe_int(payload.get("quantity"), 1))
    stock = max(0, _safe_int(payload.get("stock"), 0))

    if not category_slug or product_id <= 0:
        return None

    product_name = str(payload.get("product_name") or "").strip()[:255] or "Unknown Product"
    category_name = str(payload.get("category_name") or "").strip()[:120] or category_slug.replace("-", " ").title()

    return {
        "category_slug": category_slug,
        "category_name": category_name,
        "product_id": product_id,
        "product_name": product_name,
        "product_brand": str(payload.get("product_brand") or "").strip()[:120],
        "product_image_url": str(payload.get("product_image_url") or "").strip(),
        "unit_price": unit_price,
        "quantity": quantity,
        "stock": stock,
    }


def _shipping_payload(payload):
    data = {
        "recipient_name": str(payload.get("recipient_name") or "").strip()[:120],
        "phone": str(payload.get("phone") or "").strip()[:40],
        "address_line": str(payload.get("address_line") or "").strip()[:255],
        "city_or_region": str(payload.get("city_or_region") or "").strip()[:120],
        "postal_code": str(payload.get("postal_code") or "").strip()[:40],
        "country": str(payload.get("country") or "").strip()[:120],
        "note": str(payload.get("note") or "").strip(),
    }
    required = ["recipient_name", "phone", "address_line", "city_or_region", "postal_code", "country"]
    if any(not data[field] for field in required):
        return None
    return data


def _shipping_transition_error(order, shipping_status):
    ok, message = order.can_update_shipping_status(shipping_status)
    if ok:
        return None
    return _json_error(message, status=400)


def _resolve_range_days(raw_value):
    value = _safe_int(raw_value, 30)
    return value if value in {7, 30, 90} else 30


def _format_analytics_datetime(value):
    if value is None:
        return None
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


def _build_customer_analytics(customer_limit=200, recent_limit=20, range_days=30):
    now = timezone.localtime(timezone.now())
    start_time = now - timedelta(days=max(1, range_days))
    orders = list(
        Order.objects.filter(created_at__gte=start_time)
        .prefetch_related("items")
        .order_by("-created_at")
    )

    user_rows = {}
    daily_revenue = {}
    for offset in range(range_days - 1, -1, -1):
        day = (now - timedelta(days=offset)).date()
        daily_revenue[day] = Decimal("0")

    weekly_revenue = {}
    for day in daily_revenue:
        week_start = day - timedelta(days=day.weekday())
        weekly_revenue.setdefault(week_start, Decimal("0"))

    total_orders = 0
    paid_orders = 0
    pending_orders = 0
    cancelled_orders = 0
    total_revenue = Decimal("0")
    total_units_sold = 0
    recent_orders = []

    for order in orders:
        total_orders += 1
        items = list(order.items.all())
        units = sum(item.quantity for item in items)
        total_units_sold += units

        row = user_rows.setdefault(
            order.user_id,
            {
                "user_id": order.user_id,
                "order_count": 0,
                "paid_order_count": 0,
                "total_units": 0,
                "total_spent_value": Decimal("0"),
                "last_order_at": None,
                "recent_paid_orders": [],
            },
        )
        row["order_count"] += 1
        if row["last_order_at"] is None:
            row["last_order_at"] = _format_analytics_datetime(order.created_at)

        if order.payment_status == Order.PAYMENT_PAID:
            paid_orders += 1
            total_revenue += order.total_amount
            row["paid_order_count"] += 1
            row["total_units"] += units
            row["total_spent_value"] += order.total_amount

            order_day = timezone.localtime(order.created_at).date()
            if order_day in daily_revenue:
                daily_revenue[order_day] += order.total_amount
            week_start = order_day - timedelta(days=order_day.weekday())
            weekly_revenue.setdefault(week_start, Decimal("0"))
            weekly_revenue[week_start] += order.total_amount

            if len(row["recent_paid_orders"]) < 5:
                row["recent_paid_orders"].append(
                    {
                        "order_id": order.id,
                        "created_at": _format_analytics_datetime(order.created_at),
                        "total_amount": _decimal_str(order.total_amount),
                    }
                )
        elif order.payment_status == Order.PAYMENT_PENDING:
            pending_orders += 1
        elif order.payment_status == Order.PAYMENT_CANCELLED:
            cancelled_orders += 1

        if len(recent_orders) < max(1, recent_limit):
            recent_orders.append(
                {
                    "order_id": order.id,
                    "user_id": order.user_id,
                    "payment_status": order.payment_status,
                    "shipping_status": order.shipping_status,
                    "total_amount": _decimal_str(order.total_amount),
                    "total_units": units,
                    "created_at": _format_analytics_datetime(order.created_at),
                    "items_preview": ", ".join(f"{item.product_name} x{item.quantity}" for item in items[:3]),
                }
            )

    rows = []
    for row in user_rows.values():
        total_spent_value = row.pop("total_spent_value")
        row["total_spent"] = _decimal_str(total_spent_value)
        rows.append(row)

    rows.sort(
        key=lambda item: (
            Decimal(item["total_spent"]),
            item["order_count"],
            item["user_id"],
        ),
        reverse=True,
    )
    rows = rows[: max(1, customer_limit)]

    avg_paid_order_value = total_revenue / paid_orders if paid_orders else Decimal("0")

    return {
        "customer_count": len(user_rows),
        "active_customers": sum(1 for row in user_rows.values() if row["order_count"] > 0),
        "range_days": range_days,
        "range_start": start_time.date().isoformat(),
        "range_end": now.date().isoformat(),
        "order_stats": {
            "total_orders": total_orders,
            "paid_orders": paid_orders,
            "pending_orders": pending_orders,
            "cancelled_orders": cancelled_orders,
            "total_revenue": _decimal_str(total_revenue),
            "total_units_sold": total_units_sold,
            "average_paid_order_value": _decimal_str(avg_paid_order_value),
        },
        "top_customers": rows[:8],
        "customer_rows": rows,
        "recent_orders": recent_orders,
        "revenue_trend_daily": [
            {"label": day.strftime("%m-%d"), "revenue": _decimal_str(amount)}
            for day, amount in daily_revenue.items()
        ],
        "revenue_trend_weekly": [
            {"label": f"Week {week_start.strftime('%m-%d')}", "revenue": _decimal_str(amount)}
            for week_start, amount in weekly_revenue.items()
        ],
    }


def _build_behavior_message(order_item):
    category_phrase = order_item.category_name or order_item.category_slug or "product"
    return (
        f"I bought {order_item.product_name}. Suggest related {category_phrase.lower()} options "
        f"around ${_decimal_str(order_item.unit_price)}."
    )


def _behavior_context_for_user(user_id):
    cart_items = [
        item.product_name
        for item in CartItem.objects.filter(user_id=user_id).order_by("-updated_at")[:6]
    ]
    saved_items = [
        item.product_name
        for item in SavedItem.objects.filter(user_id=user_id).order_by("-created_at")[:6]
    ]
    recent_paid_items = [
        item.product_name
        for item in OrderItem.objects.filter(order__user_id=user_id, order__payment_status=Order.PAYMENT_PAID)
        .select_related("order")
        .order_by("-order__created_at", "-id")[:8]
    ]
    return {
        "cart_items": cart_items,
        "saved_items": saved_items,
        "recent_paid_items": recent_paid_items,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
def cart_collection_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    if request.method == "GET":
        user_id = _resolve_user_id(request)
        if user_id <= 0:
            return _json_error("user_id is required.")
        items = CartItem.objects.filter(user_id=user_id)
        return JsonResponse({"items": [_serialize_cart_item(item) for item in items]})

    payload = _parse_request_payload(request)
    user_id = _resolve_user_id(request, payload)
    item_payload = _build_item_payload(payload)
    if user_id <= 0 or not item_payload:
        return _json_error("Invalid cart payload.")

    cart_item, created = CartItem.objects.get_or_create(
        user_id=user_id,
        category_slug=item_payload["category_slug"],
        product_id=item_payload["product_id"],
        defaults={
            "category_name": item_payload["category_name"],
            "product_name": item_payload["product_name"],
            "product_brand": item_payload["product_brand"],
            "product_image_url": item_payload["product_image_url"],
            "unit_price": item_payload["unit_price"],
            "quantity": item_payload["quantity"],
        },
    )
    if not created:
        cart_item.category_name = item_payload["category_name"]
        cart_item.product_name = item_payload["product_name"]
        cart_item.product_brand = item_payload["product_brand"]
        cart_item.product_image_url = item_payload["product_image_url"]
        cart_item.unit_price = item_payload["unit_price"]
        cart_item.quantity += item_payload["quantity"]
        cart_item.save()

    return JsonResponse({"created": created, "item": _serialize_cart_item(cart_item)}, status=201 if created else 200)


@csrf_exempt
@require_http_methods(["DELETE"])
def cart_item_view(request, item_id):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    user_id = _resolve_user_id(request)
    if user_id <= 0:
        return _json_error("user_id is required.")
    item = get_object_or_404(CartItem, id=item_id, user_id=user_id)
    item.delete()
    return JsonResponse({"status": "deleted"})


@csrf_exempt
@require_http_methods(["GET"])
def saved_collection_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    user_id = _resolve_user_id(request)
    if user_id <= 0:
        return _json_error("user_id is required.")
    items = SavedItem.objects.filter(user_id=user_id)
    return JsonResponse({"items": [_serialize_saved_item(item) for item in items]})


@csrf_exempt
@require_http_methods(["POST"])
def saved_toggle_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    payload = _parse_request_payload(request)
    user_id = _resolve_user_id(request, payload)
    item_payload = _build_item_payload(payload)
    if user_id <= 0 or not item_payload:
        return _json_error("Invalid saved-item payload.")

    existing = SavedItem.objects.filter(
        user_id=user_id,
        category_slug=item_payload["category_slug"],
        product_id=item_payload["product_id"],
    ).first()
    if existing:
        existing.delete()
        return JsonResponse({"action": "removed"})

    item = SavedItem.objects.create(
        user_id=user_id,
        category_slug=item_payload["category_slug"],
        category_name=item_payload["category_name"],
        product_id=item_payload["product_id"],
        product_name=item_payload["product_name"],
        product_brand=item_payload["product_brand"],
        product_image_url=item_payload["product_image_url"],
        unit_price=item_payload["unit_price"],
    )
    return JsonResponse({"action": "saved", "item": _serialize_saved_item(item)}, status=201)


@csrf_exempt
@require_http_methods(["GET"])
def compare_collection_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    user_id = _resolve_user_id(request)
    if user_id <= 0:
        return _json_error("user_id is required.")
    items = CompareItem.objects.filter(user_id=user_id)
    return JsonResponse({"items": [_serialize_compare_item(item) for item in items]})


@csrf_exempt
@require_http_methods(["POST"])
def compare_toggle_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    payload = _parse_request_payload(request)
    user_id = _resolve_user_id(request, payload)
    item_payload = _build_item_payload(payload)
    if user_id <= 0 or not item_payload:
        return _json_error("Invalid compare payload.")

    existing = CompareItem.objects.filter(
        user_id=user_id,
        category_slug=item_payload["category_slug"],
        product_id=item_payload["product_id"],
    ).first()
    if existing:
        existing.delete()
        return JsonResponse({"action": "removed"})

    if CompareItem.objects.filter(user_id=user_id).count() >= 4:
        return _json_error("Compare list is limited to 4 items.")

    item = CompareItem.objects.create(
        user_id=user_id,
        category_slug=item_payload["category_slug"],
        category_name=item_payload["category_name"],
        product_id=item_payload["product_id"],
        product_name=item_payload["product_name"],
        product_brand=item_payload["product_brand"],
        product_image_url=item_payload["product_image_url"],
        unit_price=item_payload["unit_price"],
        stock=item_payload["stock"],
    )
    return JsonResponse({"action": "added", "item": _serialize_compare_item(item)}, status=201)


@csrf_exempt
@require_http_methods(["DELETE"])
def compare_item_view(request, item_id):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    user_id = _resolve_user_id(request)
    if user_id <= 0:
        return _json_error("user_id is required.")
    item = get_object_or_404(CompareItem, id=item_id, user_id=user_id)
    item.delete()
    return JsonResponse({"status": "deleted"})


@csrf_exempt
@require_http_methods(["POST"])
def checkout_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    payload = _parse_request_payload(request)
    user_id = _resolve_user_id(request, payload)
    shipping_data = _shipping_payload(payload)
    if user_id <= 0:
        return _json_error("user_id is required.")
    if shipping_data is None:
        return _json_error("Shipping data is required.")

    created_payment = None
    try:
        with transaction.atomic():
            cart_items = list(CartItem.objects.select_for_update().filter(user_id=user_id))
            if not cart_items:
                return _json_error("Cart is empty.")

            total_amount = sum(item.total_price for item in cart_items)
            if total_amount <= 0:
                return _json_error("Cart total must be greater than zero.")
            order = Order.objects.create(
                user_id=user_id,
                total_amount=total_amount,
                payment_status=Order.PAYMENT_PENDING,
                shipping_status=Order.SHIPPING_PENDING,
                source=Order.SOURCE_LIVE,
            )
            OrderShipping.objects.create(order=order, **shipping_data)
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        category_slug=item.category_slug,
                        category_name=item.category_name,
                        product_id=item.product_id,
                        product_name=item.product_name,
                        product_brand=item.product_brand,
                        product_image_url=item.product_image_url,
                        unit_price=item.unit_price,
                        quantity=item.quantity,
                    )
                    for item in cart_items
                ]
            )
            CartItem.objects.filter(user_id=user_id).delete()
            created_payment = create_pending_payment(order)
            try:
                create_pending_shipment(order, shipping_data)
            except DownstreamServiceError:
                cancel_payment(created_payment)
                raise
    except DownstreamServiceError as exc:
        return _json_error(exc.message, status=error_response_status(exc))

    order = Order.objects.prefetch_related("items").select_related("shipping").get(id=order.id)
    return JsonResponse({"order": _serialize_order(order)}, status=201)


@csrf_exempt
@require_http_methods(["GET"])
def orders_collection_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    user_id = _resolve_user_id(request)
    if user_id <= 0:
        return _json_error("user_id is required.")
    orders = Order.objects.filter(user_id=user_id).prefetch_related("items").select_related("shipping")
    return JsonResponse({"orders": [_serialize_order(order) for order in orders]})


@csrf_exempt
@require_http_methods(["POST"])
def pay_order_view(request, order_id):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    payload = _parse_request_payload(request)
    user_id = _resolve_user_id(request, payload)
    if user_id <= 0:
        return _json_error("user_id is required.")

    order = get_object_or_404(Order.objects.prefetch_related("items").select_related("shipping"), id=order_id, user_id=user_id)
    can_pay, message = order.can_pay()
    if not can_pay:
        return _json_error(message)

    try:
        payment = confirm_order_payment(order)
    except DownstreamServiceError as exc:
        return _json_error(exc.message, status=error_response_status(exc))

    if str(payment.get("status") or "").lower() != "paid":
        return _json_error("Payment service did not confirm payment.", status=502)

    order.payment_status = Order.PAYMENT_PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["payment_status", "paid_at", "updated_at"])
    return JsonResponse({"order": _serialize_order(order)})


@csrf_exempt
@require_http_methods(["GET"])
def staff_orders_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    limit = max(1, min(200, _safe_int(request.GET.get("limit"), 80)))
    queryset = Order.objects.prefetch_related("items").select_related("shipping").all()

    payment_status = str(request.GET.get("payment_status") or "").strip().lower()
    shipping_status = str(request.GET.get("shipping_status") or "").strip().lower()
    if payment_status in Order.PAYMENT_VALUES:
        queryset = queryset.filter(payment_status=payment_status)
    if shipping_status in Order.SHIPPING_VALUES:
        queryset = queryset.filter(shipping_status=shipping_status)

    orders = list(queryset[:limit])
    return JsonResponse({"orders": [_serialize_order(order) for order in orders]})


@csrf_exempt
@require_http_methods(["POST"])
def staff_shipping_update_view(request, order_id):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    payload = _parse_request_payload(request)
    shipping_status = str(payload.get("shipping_status") or "").strip().lower()
    if shipping_status not in Order.SHIPPING_VALUES:
        return _json_error("Invalid shipping status.")

    order = get_object_or_404(Order.objects.prefetch_related("items").select_related("shipping"), id=order_id)
    transition_error = _shipping_transition_error(order, shipping_status)
    if transition_error is not None:
        return transition_error
    try:
        shipment = update_order_shipment_status(order, shipping_status, _order_shipping_payload(order))
    except DownstreamServiceError as exc:
        return _json_error(exc.message, status=error_response_status(exc))
    upstream_status = str(shipment.get("status") or shipping_status).strip().lower()
    if upstream_status not in Order.SHIPPING_VALUES:
        return _json_error("Shipping service returned an invalid status.", status=502)
    shipping_status = upstream_status
    order.shipping_status = shipping_status
    order.save(update_fields=["shipping_status", "updated_at"])
    return JsonResponse({"order": _serialize_order(order)})


@csrf_exempt
@require_http_methods(["GET"])
def customer_analytics_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    customer_limit = max(20, min(1000, _safe_int(request.GET.get("customer_limit"), 200)))
    recent_limit = max(5, min(100, _safe_int(request.GET.get("recent_limit"), 20)))
    range_days = _resolve_range_days(request.GET.get("range_days"))
    return JsonResponse(
        _build_customer_analytics(
            customer_limit=customer_limit,
            recent_limit=recent_limit,
            range_days=range_days,
        )
    )


@csrf_exempt
@require_http_methods(["GET"])
def behavior_source_view(request):
    auth_error = _require_internal_access(request)
    if auth_error is not None:
        return auth_error
    max_users = max(1, min(1000, _safe_int(request.GET.get("max_users"), 300)))
    max_events = max(1, min(5000, _safe_int(request.GET.get("max_events"), 1200)))
    source_status = str(request.GET.get("source_status") or "paid").strip().lower()

    queryset = Order.objects.prefetch_related("items")
    if source_status == "paid":
        queryset = queryset.filter(payment_status=Order.PAYMENT_PAID)
    queryset = queryset.order_by("-created_at")

    selected_user_ids = []
    seen_user_ids = set()
    selected_orders = []
    for order in queryset:
        if order.user_id not in seen_user_ids:
            if len(selected_user_ids) >= max_users:
                continue
            seen_user_ids.add(order.user_id)
            selected_user_ids.append(order.user_id)
        if order.user_id in seen_user_ids:
            selected_orders.append(order)
        if len(selected_orders) >= max_events:
            break

    records = []
    for order in selected_orders:
        user_context = _behavior_context_for_user(order.user_id)
        for item in order.items.all():
            records.append(
                {
                    "user_ref": str(order.user_id),
                    "message": _build_behavior_message(item),
                    "current_product": {
                        "category_slug": item.category_slug,
                        "category_name": item.category_name,
                        "service": item.category_slug,
                        "id": item.product_id,
                        "name": item.product_name,
                        "brand": item.product_brand,
                        "price": _decimal_str(item.unit_price),
                    },
                    "user_context": user_context,
                }
            )
            if len(records) >= max_events:
                break
        if len(records) >= max_events:
            break

    return JsonResponse({"records": records})
