from decimal import Decimal, InvalidOperation
import json
import os

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from .api_gateway import build_gateway_registry
from .auth_rules import can_access_customer
from .content import FAQ_ITEMS
from .forms import CustomerLoginForm, CustomerRegisterForm, ProductFilterForm
from .models import BlogPost, Testimonial
from .services import (
    DEFAULT_CATEGORY_HERO,
    add_to_cart,
    build_cart_ai_suggestions,
    build_dashboard_ai_suggestions,
    build_staff_analytics_payload,
    build_user_context_payload,
    category_choice_pairs,
    checkout_order,
    fetch_categories,
    fetch_category_lookup,
    fetch_product_detail,
    fetch_products,
    get_available_brands,
    list_cart_items,
    list_compare_items,
    list_orders,
    list_saved_items,
    pay_order,
    recommend_products_for_detail,
    remove_compare_item,
    remove_from_cart,
    request_chatbot_reply,
    toggle_compare_item,
    toggle_saved_item,
)

User = get_user_model()


def _is_customer_user(user):
    return can_access_customer(user)


def gateway_dashboard_view(request):
    gateway = build_gateway_registry(request)
    return render(
        request,
        "customer/gateway_dashboard.html",
        {
            "gateway": gateway,
            "gateway_json": json.dumps(gateway),
        },
    )


def gateway_apis_view(request):
    return JsonResponse(build_gateway_registry(request))


def _safe_next_url(next_url, fallback):
    next_url = (next_url or "").strip()
    return next_url if next_url.startswith("/") else fallback


def _dashboard_url(request, updates=None, anchor=None):
    updates = updates or {}
    query = request.GET.copy()
    for key, value in updates.items():
        if value in [None, ""]:
            query.pop(key, None)
        else:
            query[key] = str(value)

    encoded = query.urlencode()
    url = "/customer/dashboard/"
    if encoded:
        url += f"?{encoded}"
    if anchor:
        url += f"#{anchor}"
    return url


def _customer_shell_context():
    categories = fetch_categories()
    category_sections = [
        {
            "title": item["name"],
            "description": item.get("description") or f"Browse products from the {item['name']} catalog.",
            "query": item["slug"],
            "hero_image_url": item.get("hero_image_url") or DEFAULT_CATEGORY_HERO,
        }
        for item in categories[:6]
    ]
    return {
        "category_sections": category_sections,
        "category_navigation": categories,
    }


def _render_customer(request, template_name, context=None):
    payload = _customer_shell_context()
    payload.update(context or {})
    return render(request, template_name, payload)


def _default_filters():
    return {
        "q": "",
        "category": "all",
        "stock": "all",
        "price_range": "all",
        "sort": "newest",
        "brand": "all",
    }


def _collect_filters(request):
    filters = _default_filters()
    for key in filters:
        value = request.GET.get(key)
        if value not in [None, ""]:
            filters[key] = value

    legacy_service = (request.GET.get("service") or "").strip().lower()
    if legacy_service and filters["category"] == "all":
        filters["category"] = legacy_service

    brand_scope_filters = dict(filters)
    brand_scope_filters["brand"] = "all"
    brand_scope_filters["sort"] = "newest"
    brand_source_products = fetch_products(brand_scope_filters)
    available_brands = get_available_brands(brand_source_products)
    category_choices = category_choice_pairs()

    form = ProductFilterForm(
        request.GET or None,
        brand_choices=available_brands,
        category_choices=category_choices,
    )
    if form.is_valid():
        for key in filters:
            value = form.cleaned_data.get(key)
            if value not in [None, ""]:
                filters[key] = value

    return form, filters, available_brands


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _decimal_to_str(value):
    return f"{(value or Decimal('0')):.2f}"


def _parse_product_payload(request):
    category_slug = (request.POST.get("category_slug") or request.POST.get("product_service") or "").strip().lower()
    if not category_slug:
        return None

    try:
        product_id = int(request.POST.get("product_id", "0"))
        price = Decimal(str(request.POST.get("unit_price", "0")))
        stock = int(request.POST.get("stock", "0") or 0)
    except (TypeError, ValueError, InvalidOperation):
        return None

    category_name = (request.POST.get("category_name") or category_slug.replace("-", " ").title()).strip()[:120]
    product_name = (request.POST.get("product_name", "") or "").strip()[:255] or "Unknown Product"
    return {
        "category_slug": category_slug,
        "category_name": category_name,
        "product_id": product_id,
        "product_name": product_name,
        "product_brand": (request.POST.get("product_brand", "") or "").strip()[:120],
        "product_image_url": (request.POST.get("product_image_url", "") or "").strip(),
        "unit_price": price,
        "stock": max(0, stock),
    }


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
        "category_name": str(current_product.get("category_name") or category_slug.replace("-", " ").title()).strip()[:120],
        "service": category_slug,
        "id": product_id,
        "name": str(current_product.get("name") or "").strip()[:255],
        "brand": str(current_product.get("brand") or "").strip()[:120],
        "price": str(current_product.get("price") or "0").strip(),
    }


def _resolve_range_days(raw_value):
    value = _safe_int(raw_value, 30)
    return value if value in {7, 30, 90} else 30


def _format_trend_rows(series):
    max_value = Decimal("0")
    for point in series or []:
        revenue = Decimal(str(point.get("revenue") or "0"))
        if revenue > max_value:
            max_value = revenue

    rows = []
    for point in series or []:
        revenue = Decimal(str(point.get("revenue") or "0"))
        pct = int(round((revenue / max_value) * 100)) if max_value > 0 else 0
        rows.append({"label": point.get("label") or "N/A", "revenue": _decimal_to_str(revenue), "pct": pct})
    return rows


def home_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("/admin/")
        return redirect("customer_dashboard")
    return redirect("customer_login")


def customer_login_view(request):
    if _is_customer_user(request.user):
        return redirect("customer_dashboard")

    form = CustomerLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.is_superuser:
            messages.error(request, "Admin accounts should sign in via /admin/.")
            return render(request, "customer/login.html", {"form": form})

        if user.is_staff:
            messages.error(request, "Staff accounts should sign in via /staff/login/.")
            return redirect("staff_login")
        login(request, user)
        return redirect("customer_dashboard")

    return render(request, "customer/login.html", {"form": form})


def customer_register_view(request):
    form = CustomerRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )
        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=["is_staff", "is_superuser"])
        messages.success(request, "Registration successful. Please sign in.")
        return redirect("customer_login")

    return render(request, "customer/register.html", {"form": form})


@login_required
def customer_logout_view(request):
    logout(request)
    return redirect("customer_login")


@login_required
@user_passes_test(_is_customer_user)
def customer_dashboard_view(request):
    filter_form, filters, available_brands = _collect_filters(request)
    products = fetch_products(filters)
    cart_items = list_cart_items(request.user.id)
    saved_items = list_saved_items(request.user.id)
    orders = list_orders(request.user.id)
    user_context_payload = build_user_context_payload(
        request.user.id,
        cart_items=cart_items,
        saved_items=saved_items,
        orders=orders,
    )
    saved_pairs = {
        (item.get("category_slug") or item.get("product_service"), item.get("product_id"))
        for item in saved_items
    }
    for product in products:
        product["is_saved"] = (product.get("category_slug"), _safe_int(product.get("id"), 0)) in saved_pairs

    product_page = Paginator(products, 9).get_page(request.GET.get("product_page") or 1)
    blog_page = Paginator(BlogPost.objects.all(), 3).get_page(request.GET.get("blog_page") or 1)
    best_sellers = sorted(fetch_products({"category": "all", "sort": "newest"}), key=lambda p: p.get("stock", 0), reverse=True)[:6]
    dashboard_ai = build_dashboard_ai_suggestions(
        request.user.id,
        filters=filters,
        products=products,
        user_context=user_context_payload,
        limit=4,
    )
    if dashboard_ai:
        dashboard_ai = {
            **dashboard_ai,
            "badge": "AI Search Layer",
            "title": "AI goi y cho ban",
        }

    context = {
        "filter_form": filter_form,
        "products_page": product_page,
        "best_sellers": best_sellers,
        "available_brands": available_brands,
        "cart_count": len(cart_items),
        "filters": filters,
        "testimonials": Testimonial.objects.filter(is_featured=True)[:6],
        "blog_page": blog_page,
        "faq_items": FAQ_ITEMS,
        "dashboard_ai": dashboard_ai,
        "product_prev_url": _dashboard_url(
            request,
            {"product_page": product_page.previous_page_number() if product_page.has_previous() else None},
            "section-products",
        ),
        "product_next_url": _dashboard_url(
            request,
            {"product_page": product_page.next_page_number() if product_page.has_next() else None},
            "section-products",
        ),
        "blog_prev_url": _dashboard_url(
            request,
            {"blog_page": blog_page.previous_page_number() if blog_page.has_previous() else None},
            "section-stories",
        ),
        "blog_next_url": _dashboard_url(
            request,
            {"blog_page": blog_page.next_page_number() if blog_page.has_next() else None},
            "section-stories",
        ),
    }
    return _render_customer(request, "customer/dashboard.html", context)


@login_required
@user_passes_test(_is_customer_user)
@require_POST
def chatbot_reply_view(request):
    payload = _parse_request_payload(request)
    message = str(payload.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "Message is required."}, status=400)

    current_product = _extract_current_product(payload)
    result = request_chatbot_reply(
        question=message[:500],
        current_product=current_product,
        user_context=build_user_context_payload(request.user.id),
        user_ref=str(request.user.id),
        limit=5,
    )

    recommendations = []
    for item in result.get("recommendations", []):
        category_slug = str(item.get("category_slug") or item.get("service") or "").strip().lower()
        product_id = _safe_int(item.get("id"), 0)
        if not category_slug or product_id <= 0:
            continue
        recommendations.append(
            {
                "service": category_slug,
                "category_slug": category_slug,
                "category_name": item.get("category_name") or category_slug.replace("-", " ").title(),
                "id": product_id,
                "name": item.get("name") or "N/A",
                "brand": item.get("brand") or "",
                "price": item.get("price") or "0",
                "stock": _safe_int(item.get("stock"), 0),
                "image_url": item.get("image_url") or "",
                "url": f"/customer/products/{category_slug}/{product_id}/",
            }
        )

    return JsonResponse(
        {
            "answer": result.get("answer") or "No response generated.",
            "recommendations": recommendations,
            "citations": result.get("citations") or [],
            "source": result.get("source") or "rule_based",
            "fallback_used": bool(result.get("fallback_used")),
            "error_code": result.get("error_code"),
            "provider": result.get("provider"),
        }
    )


@login_required
@user_passes_test(_is_customer_user)
def blog_detail_view(request, slug):
    blog_post = get_object_or_404(BlogPost, slug=slug)
    related_posts = BlogPost.objects.exclude(id=blog_post.id)[:4]
    return _render_customer(
        request,
        "customer/blog_detail.html",
        {"blog_post": blog_post, "related_posts": related_posts},
    )


@login_required
@user_passes_test(_is_customer_user)
@require_POST
def add_to_cart_view(request):
    payload = _parse_product_payload(request)
    next_url = _safe_next_url(request.POST.get("next"), "/customer/dashboard/")
    if not payload:
        messages.error(request, "Invalid product data.")
        return redirect(next_url)

    ok, _, error = add_to_cart(request.user.id, payload)
    if ok:
        messages.success(request, f"Added '{payload['product_name']}' to cart.")
    else:
        messages.error(request, error or "Unable to add item to cart.")
    return redirect(next_url)


@login_required
@user_passes_test(_is_customer_user)
@require_POST
def toggle_save_view(request):
    payload = _parse_product_payload(request)
    next_url = _safe_next_url(request.POST.get("next"), "/customer/dashboard/")
    if not payload:
        messages.error(request, "Unable to save this product.")
        return redirect(next_url)

    ok, data, error = toggle_saved_item(request.user.id, payload)
    if ok and data.get("action") == "removed":
        messages.success(request, "Removed from saved items.")
    elif ok:
        messages.success(request, "Saved for later.")
    else:
        messages.error(request, error or "Unable to save this product.")
    return redirect(next_url)


@login_required
@user_passes_test(_is_customer_user)
@require_POST
def toggle_compare_view(request):
    payload = _parse_product_payload(request)
    next_url = _safe_next_url(request.POST.get("next"), "/customer/dashboard/")
    if not payload:
        messages.error(request, "Unable to compare this product.")
        return redirect(next_url)

    ok, data, error = toggle_compare_item(request.user.id, payload)
    if ok and data.get("action") == "removed":
        messages.success(request, "Removed from compare list.")
    elif ok:
        messages.success(request, "Added to compare list.")
    else:
        messages.error(request, error or "Unable to compare this product.")
    return redirect(next_url)


@login_required
@user_passes_test(_is_customer_user)
def saved_view(request):
    return _render_customer(request, "customer/saved.html", {"saved_items": list_saved_items(request.user.id)})


@login_required
@user_passes_test(_is_customer_user)
def compare_view(request):
    return _render_customer(request, "customer/compare.html", {"compare_items": list_compare_items(request.user.id)})


@login_required
@user_passes_test(_is_customer_user)
@require_POST
def remove_compare_item_view(request, item_id):
    ok, error = remove_compare_item(request.user.id, item_id)
    if ok:
        messages.success(request, "Item removed from compare list.")
    else:
        messages.error(request, error or "Unable to remove compare item.")
    return redirect("customer_compare")


@login_required
@user_passes_test(_is_customer_user)
def product_detail_view(request, category_slug, product_id):
    product = fetch_product_detail(category_slug, product_id)
    if not product:
        messages.error(request, "Product not found.")
        return redirect("customer_dashboard")

    rec_mode = (request.GET.get("rec_mode") or "mixed").strip().lower()
    if rec_mode not in {"mixed", "similar"}:
        rec_mode = "mixed"

    related_products = recommend_products_for_detail(
        current_product=product,
        cart_items=list_cart_items(request.user.id),
        limit=6,
        mode=rec_mode,
    )
    category_lookup = fetch_category_lookup()
    category_meta = category_lookup.get(product.get("category_slug"), {})
    base_image = product.get("image_url") or category_meta.get("hero_image_url") or DEFAULT_CATEGORY_HERO
    product = {
        **product,
        "image_fallback_url": product.get("image_fallback_url")
        or category_meta.get("hero_image_url")
        or DEFAULT_CATEGORY_HERO,
    }
    gallery_pool = [
        category_meta.get("hero_image_url") or DEFAULT_CATEGORY_HERO,
        "https://images.unsplash.com/photo-1498049794561-7780e7231661?auto=format&fit=crop&w=1400&q=80",
        "https://images.unsplash.com/photo-1496171367470-9ed9a91ea931?auto=format&fit=crop&w=1400&q=80",
        "https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=1400&q=80",
    ]
    gallery_images = [base_image] + [image for image in gallery_pool if image and image != base_image][:3]
    while len(gallery_images) < 4:
        gallery_images.append(base_image)

    saved_items = list_saved_items(request.user.id)
    compare_items = list_compare_items(request.user.id)
    is_saved = any(
        (item.get("category_slug") or item.get("product_service")) == product["category_slug"]
        and item.get("product_id") == product_id
        for item in saved_items
    )
    is_compared = any(
        (item.get("category_slug") or item.get("product_service")) == product["category_slug"]
        and item.get("product_id") == product_id
        for item in compare_items
    )

    return _render_customer(
        request,
        "customer/product_detail.html",
        {
            "product": product,
            "related_products": related_products,
            "gallery_images": gallery_images,
            "is_saved": is_saved,
            "is_compared": is_compared,
            "compare_count": len(compare_items),
            "share_url": request.build_absolute_uri(request.path),
            "chatbot_current_product": {
                **product,
                "service": product["category_slug"],
            },
            "rec_mode": rec_mode,
            "rec_mode_mixed_url": f"{request.path}?rec_mode=mixed#section-recommend-products",
            "rec_mode_similar_url": f"{request.path}?rec_mode=similar#section-recommend-products",
        },
    )


@login_required
@user_passes_test(_is_customer_user)
def cart_view(request):
    cart_items = list_cart_items(request.user.id)
    cart_total = sum(Decimal(str(item.get("total_price") or "0")) for item in cart_items)
    cart_recommendations = build_cart_ai_suggestions(request.user.id, cart_items, limit=4) if cart_items else None
    return _render_customer(
        request,
        "customer/cart.html",
        {
            "cart_items": cart_items,
            "cart_total": cart_total,
            "cart_recommendations": cart_recommendations,
        },
    )


@login_required
@user_passes_test(_is_customer_user)
@require_POST
def remove_from_cart_view(request, item_id):
    ok, error = remove_from_cart(request.user.id, item_id)
    if ok:
        messages.success(request, "Item removed from your cart.")
    else:
        messages.error(request, error or "Unable to remove cart item.")
    return redirect("customer_cart")


@login_required
@user_passes_test(_is_customer_user)
@require_POST
def checkout_view(request):
    shipping_data = {
        "recipient_name": request.POST.get("recipient_name"),
        "phone": request.POST.get("phone"),
        "address_line": request.POST.get("address_line"),
        "city_or_region": request.POST.get("city_or_region"),
        "postal_code": request.POST.get("postal_code"),
        "country": request.POST.get("country"),
        "note": request.POST.get("note", ""),
    }
    ok, order, error = checkout_order(request.user.id, shipping_data)
    if ok:
        messages.success(request, f"Order #{order['id']} was created with payment PENDING and shipping PENDING.")
        return redirect("customer_orders")
    messages.error(request, error or "Checkout failed. Please review your shipping information.")
    return redirect("customer_cart")


@login_required
@user_passes_test(_is_customer_user)
def orders_view(request):
    return _render_customer(request, "customer/orders.html", {"orders": list_orders(request.user.id)})


@login_required
@user_passes_test(_is_customer_user)
@require_POST
def pay_order_view(request, order_id):
    ok, order, error = pay_order(request.user.id, order_id)
    if ok:
        messages.success(request, f"Payment completed successfully for order #{order['id']}.")
    else:
        messages.error(request, error or f"Order #{order_id} could not be paid.")
    return redirect("customer_orders")


@require_http_methods(["GET"])
def staff_order_analytics_view(request):
    provided_key = (request.headers.get("X-Staff-Key") or "").strip()
    expected_key = (os.getenv("STAFF_API_KEY") or "dev-staff-key").strip()
    if provided_key != expected_key:
        return JsonResponse({"error": "Forbidden"}, status=403)

    range_days = _resolve_range_days(request.GET.get("range_days"))
    customer_limit = max(20, min(1000, _safe_int(request.GET.get("customer_limit"), 200)))
    recent_limit = max(5, min(100, _safe_int(request.GET.get("recent_limit"), 20)))
    payload = build_staff_analytics_payload(
        customer_limit=customer_limit,
        recent_limit=recent_limit,
        range_days=range_days,
    )
    payload["revenue_trend_daily_rows"] = _format_trend_rows(payload.get("revenue_trend_daily"))
    payload["revenue_trend_weekly_rows"] = _format_trend_rows(payload.get("revenue_trend_weekly"))
    payload["selected_range_days"] = range_days
    payload["time_ranges"] = [7, 30, 90]
    return JsonResponse(payload)
