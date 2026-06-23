import json
import os

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .behavior_ai import record_behavior_event
from .services import (
    generate_chatbot_response,
    get_active_llm_provider,
    parse_provider_control_command,
    set_active_llm_provider,
)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_request_payload(request):
    if "application/json" in (request.content_type or "").lower():
        try:
            return json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    return request.POST.dict()


def _extract_current_product(payload):
    current_product = payload.get("current_product")
    if not isinstance(current_product, dict):
        return None

    category_slug = str(current_product.get("category_slug") or current_product.get("service") or "").strip().lower()
    product_id = _safe_int(current_product.get("id"), 0)
    if not category_slug or product_id <= 0:
        return None

    return {
        "category_slug": category_slug,
        "category_name": str(current_product.get("category_name") or "").strip()[:120],
        "service": category_slug,
        "id": product_id,
        "name": str(current_product.get("name") or "").strip()[:255],
        "brand": str(current_product.get("brand") or "").strip()[:120],
        "price": str(current_product.get("price") or "0").strip(),
    }


def _extract_user_context(payload):
    user_context = payload.get("user_context")
    if not isinstance(user_context, dict):
        return {}

    normalized = {}
    for key in ["cart_items", "saved_items", "recent_paid_items"]:
        values = user_context.get(key)
        if not isinstance(values, list):
            normalized[key] = []
            continue
        normalized[key] = [str(value).strip()[:255] for value in values if str(value).strip()][:15]
    return normalized


@require_POST
@csrf_exempt
def chat_reply_view(request):
    payload = _parse_request_payload(request)
    message = str(payload.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "Message is required."}, status=400)

    message = message[:500]
    control_action, control_provider = parse_provider_control_command(message)
    if control_action == "show":
        active_provider = get_active_llm_provider()
        return JsonResponse(
            {
                "answer": f"Provider hien tai: {active_provider}. Dung /model gemma hoac /model gemini de chuyen nhanh.",
                "recommendations": [],
                "citations": [],
                "source": "provider_control",
                "fallback_used": False,
                "error_code": None,
                "provider": active_provider,
            }
        )

    if control_action == "set" and control_provider:
        active_provider = set_active_llm_provider(control_provider)
        if not active_provider:
            return JsonResponse({"error": "Unable to switch provider right now."}, status=500)
        return JsonResponse(
            {
                "answer": f"Da chuyen provider sang {active_provider}. Tin nhan tiep theo se dung model nay.",
                "recommendations": [],
                "citations": [],
                "source": "provider_control",
                "fallback_used": False,
                "error_code": None,
                "provider": active_provider,
            }
        )

    result = generate_chatbot_response(
        question=message,
        current_product=_extract_current_product(payload),
        user_context=_extract_user_context(payload),
        user_ref=str(payload.get("user_ref") or "").strip() or "anonymous",
        limit=max(1, min(8, _safe_int(payload.get("limit"), 5))),
    )
    return JsonResponse(result)


@require_POST
@csrf_exempt
def ingest_behavior_event_view(request):
    expected_key = (os.getenv("CHATBOT_INGEST_KEY") or "").strip()
    if expected_key:
        provided_key = (request.headers.get("X-Ingest-Key") or "").strip()
        if provided_key != expected_key:
            return JsonResponse({"error": "Forbidden"}, status=403)

    payload = _parse_request_payload(request)
    message = str(payload.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "Message is required."}, status=400)

    record_behavior_event(
        user_ref=str(payload.get("user_ref") or "").strip() or "anonymous",
        message=message[:500],
        current_product=_extract_current_product(payload),
        user_context=_extract_user_context(payload),
    )
    return JsonResponse({"status": "ok"})
