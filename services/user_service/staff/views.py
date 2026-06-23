from collections import defaultdict
from decimal import Decimal, InvalidOperation

import secrets
import string

import requests
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from customer.services import (
    build_staff_analytics_payload,
    category_choice_pairs,
    fetch_categories,
    fetch_products,
    fetch_staff_orders,
    update_shipping_status,
)
from customer.auth_rules import can_access_staff
from .forms import CreateItemForm, CustomerEditForm, DeleteItemForm, StaffLoginForm, StaffRegisterForm, UpdateItemForm

User = get_user_model()

SHIPPING_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("preparing", "Preparing"),
    ("shipped", "Shipped"),
    ("delivered", "Delivered"),
    ("cancelled", "Cancelled"),
]


def _is_staff_user(user):
    return can_access_staff(user)


def _product_service_url():
    from customer.services import _product_service_url  # local import to avoid circular import at module load time

    return _product_service_url()


def _staff_headers():
    import os

    return {"X-Staff-Key": os.getenv("STAFF_API_KEY", "dev-staff-key")}


def _request_json(method, url, *, payload=None, timeout=8):
    try:
        response = requests.request(method=method, url=url, json=payload, headers=_staff_headers(), timeout=timeout)
        data = response.json() if response.content else {}
    except (requests.RequestException, ValueError):
        return False, {}, "service_unavailable"
    return response.ok, data if isinstance(data, dict) else {}, None if response.ok else data.get("error")


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _resolve_category_filter(raw_value, category_choices):
    allowed = {"all", *(slug for slug, _ in category_choices)}
    value = (raw_value or "").strip().lower()
    return value if value in allowed else "all"


def _category_label(category_slug, category_choices):
    if category_slug == "all":
        return "All categories"
    for slug, label in category_choices:
        if slug == category_slug:
            return label
    return category_slug.replace("-", " ").title()


def _build_dashboard_stats():
    items = fetch_products({"category": "all", "sort": "newest"})
    category_stats = defaultdict(lambda: {"count": 0, "stock": 0, "category_name": ""})
    total_stock = 0
    total_value = Decimal("0")
    low_stock_items = 0

    for item in items:
        category_slug = item.get("category_slug")
        category_name = item.get("category_name") or category_slug.replace("-", " ").title()
        stock = _to_int(item.get("stock"))
        price = _to_decimal(item.get("price"))
        total_stock += stock
        total_value += price * Decimal(stock)
        if stock <= 5:
            low_stock_items += 1

        category_stats[category_slug]["count"] += 1
        category_stats[category_slug]["stock"] += stock
        category_stats[category_slug]["category_name"] = category_name

    breakdown = []
    for category_slug, row in category_stats.items():
        breakdown.append(
            {
                "service": category_slug,
                "category_slug": category_slug,
                "category_name": row["category_name"],
                "count": row["count"],
                "stock": row["stock"],
                "count_pct": int(round((row["count"] / max(1, len(items))) * 100)),
                "stock_pct": int(round((row["stock"] / max(1, total_stock)) * 100)) if total_stock else 0,
            }
        )
    breakdown.sort(key=lambda row: (row["count"], row["stock"], row["category_slug"]), reverse=True)

    return {
        "total_items": len(items),
        "total_stock": total_stock,
        "total_inventory_value": total_value,
        "low_stock_items": low_stock_items,
        "service_breakdown": breakdown[:10],
        "max_service_count": max([row["count"] for row in breakdown] or [1]),
        "max_service_stock": max([row["stock"] for row in breakdown] or [1]),
        "recent_items": items[:8],
    }


def _product_payload(cleaned_data, category_map):
    category_slug = cleaned_data["service"]
    category_id = category_map.get(category_slug)
    if not category_id:
        return None
    return {
        "category": category_id,
        "name": cleaned_data["name"],
        "brand": cleaned_data["brand"],
        "description": cleaned_data.get("description", ""),
        "image_url": cleaned_data.get("image_url", ""),
        "price": str(cleaned_data["price"]),
        "stock": cleaned_data["stock"],
    }


def staff_login_view(request):
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("/admin/")
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("staff_dashboard")

    form = StaffLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.is_superuser:
            messages.error(request, "Admin accounts should sign in via /admin/.")
        elif not user.is_staff:
            messages.error(request, "This account does not have Staff access.")
        else:
            login(request, user)
            return redirect("staff_dashboard")
    return render(request, "staff/login.html", {"form": form})


def staff_register_view(request):
    form = StaffRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )
        user.is_staff = True
        user.is_superuser = False
        user.save(update_fields=["is_staff", "is_superuser"])
        messages.success(request, "Staff account created successfully. Please sign in.")
        return redirect("staff_login")
    return render(request, "staff/register.html", {"form": form})


@login_required(login_url="staff_login")
def staff_logout_view(request):
    logout(request)
    return redirect("staff_login")


@login_required(login_url="staff_login")
@user_passes_test(_is_staff_user, login_url="staff_login")
@require_http_methods(["GET"])
def staff_dashboard_view(request):
    range_days = _to_int(request.GET.get("range")) or 30
    if range_days not in {7, 30, 90}:
        range_days = 30
    context = _build_dashboard_stats()
    context.update(build_staff_analytics_payload(customer_limit=120, recent_limit=12, range_days=range_days))
    context["selected_range_days"] = range_days
    context["time_ranges"] = [7, 30, 90]
    return render(request, "staff/dashboard.html", context)


@login_required(login_url="staff_login")
@user_passes_test(_is_staff_user, login_url="staff_login")
@require_http_methods(["GET"])
def staff_customers_view(request):
    range_days = _to_int(request.GET.get("range")) or 30
    if range_days not in {7, 30, 90}:
        range_days = 30
    context = build_staff_analytics_payload(customer_limit=220, recent_limit=30, range_days=range_days)
    query = (request.GET.get("q") or "").strip().lower()
    rows = context.get("customer_rows") or []
    if query:
        rows = [
            row
            for row in rows
            if query in (row.get("username") or "").lower()
            or query in (row.get("email") or "").lower()
            or query in (row.get("display_name") or "").lower()
            or query in (row.get("full_name") or "").lower()
        ]

    rows_page = Paginator(rows, 24).get_page(request.GET.get("page") or 1)
    context["customer_rows_page"] = rows_page
    context["history_customers"] = [row for row in rows_page.object_list if _to_int(row.get("paid_order_count")) > 0][:10]
    context["customer_query"] = query
    context["filtered_customer_count"] = len(rows)
    context["selected_range_days"] = range_days
    context["time_ranges"] = [7, 30, 90]
    return render(request, "staff/customers.html", context)


@login_required(login_url="staff_login")
@user_passes_test(_is_staff_user, login_url="staff_login")
@require_http_methods(["GET", "POST"])
def staff_items_view(request):
    categories = fetch_categories()
    category_choices = [(item["slug"], item["name"]) for item in categories]
    category_map = {item["slug"]: item.get("id") for item in categories}
    selected_category = _resolve_category_filter(request.GET.get("category") or request.GET.get("service"), category_choices)

    initial_category = selected_category if selected_category != "all" else (category_choices[0][0] if category_choices else "")
    create_form = CreateItemForm(prefix="create", service_choices=category_choices, initial={"service": initial_category})
    update_form = UpdateItemForm(prefix="update", service_choices=category_choices)

    if request.method == "POST":
        intent = (request.POST.get("intent") or "").strip().lower()
        return_category = _resolve_category_filter(request.POST.get("return_category") or request.POST.get("return_service") or selected_category, category_choices)

        if intent == "create":
            create_form = CreateItemForm(request.POST, prefix="create", service_choices=category_choices)
            if create_form.is_valid():
                payload = _product_payload(create_form.cleaned_data, category_map)
                ok, _, error = _request_json("POST", f"{_product_service_url()}/api/products/", payload=payload)
                if ok:
                    messages.success(request, "Created new product successfully.")
                else:
                    messages.error(request, error or "Unable to create product.")
            else:
                messages.error(request, "Please fill all required fields to create a product.")

        elif intent == "update":
            update_form = UpdateItemForm(request.POST, prefix="update", service_choices=category_choices)
            if update_form.is_valid():
                payload = _product_payload(update_form.cleaned_data, category_map)
                ok, _, error = _request_json(
                    "PUT",
                    f"{_product_service_url()}/api/products/{update_form.cleaned_data['product_id']}/",
                    payload=payload,
                )
                if ok:
                    messages.success(request, "Updated product successfully.")
                else:
                    messages.error(request, error or "Unable to update product.")
            else:
                messages.error(request, "Selected product data is invalid for update.")

        elif intent == "delete":
            delete_form = DeleteItemForm(request.POST, prefix="delete", service_choices=category_choices)
            if delete_form.is_valid():
                ok, _, error = _request_json(
                    "DELETE",
                    f"{_product_service_url()}/api/products/{delete_form.cleaned_data['product_id']}/",
                )
                if ok:
                    messages.success(request, "Deleted product successfully.")
                else:
                    messages.error(request, error or "Unable to delete product.")
            else:
                messages.error(request, "Delete request is invalid.")
        else:
            messages.error(request, "Unknown action requested.")

        return redirect(f"/staff/items/?category={return_category}")

    items = fetch_products({"category": selected_category, "sort": "newest"})
    context = {
        "create_form": create_form,
        "update_form": update_form,
        "items": items,
        "selected_category": selected_category,
        "selected_category_label": _category_label(selected_category, category_choices),
        "category_choices": category_choices,
        "category_filter_choices": [("all", "All categories"), *category_choices],
    }
    return render(request, "staff/items.html", context)


@login_required(login_url="staff_login")
@user_passes_test(_is_staff_user, login_url="staff_login")
def staff_orders_view(request):
    if request.method == "POST":
        order_id = _to_int(request.POST.get("order_id"))
        shipping_status = (request.POST.get("shipping_status") or "").strip().lower()
        ok, _, error = update_shipping_status(order_id, shipping_status)
        if ok:
            messages.success(request, f"Updated shipping status for order #{order_id}.")
        else:
            messages.error(request, error or "Unable to update shipping status.")
        return redirect("/staff/orders/")

    selected_shipping = (request.GET.get("shipping_status") or "").strip().lower()
    selected_payment = (request.GET.get("payment_status") or "").strip().lower()
    orders = fetch_staff_orders(limit=120, payment_status=selected_payment, shipping_status=selected_shipping)
    return render(
        request,
        "staff/orders.html",
        {
            "orders": orders,
            "shipping_status_choices": SHIPPING_STATUS_CHOICES,
            "selected_shipping_status": selected_shipping,
            "selected_payment_status": selected_payment,
        },
    )


@login_required(login_url="staff_login")
@user_passes_test(_is_staff_user, login_url="staff_login")
@require_http_methods(["GET"])
def staff_customer_detail_view(request, user_id):
    customer = get_object_or_404(User, id=user_id, is_staff=False, is_superuser=False)
    analytics = build_staff_analytics_payload(customer_limit=500, recent_limit=50, range_days=90)
    customer_row = next(
        (row for row in analytics.get("customer_rows", []) if row.get("user_id") == user_id),
        {},
    )
    customer_orders = [
        order for order in analytics.get("recent_orders", []) if order.get("user_id") == user_id
    ]
    return render(
        request,
        "staff/customer_detail.html",
        {
            "customer": customer,
            "customer_row": customer_row,
            "customer_orders": customer_orders,
        },
    )


@login_required(login_url="staff_login")
@user_passes_test(_is_staff_user, login_url="staff_login")
@require_http_methods(["GET", "POST"])
def staff_customer_edit_view(request, user_id):
    customer = get_object_or_404(User, id=user_id, is_staff=False, is_superuser=False)
    if request.method == "POST":
        form = CustomerEditForm(request.POST, instance_user=customer)
        if form.is_valid():
            customer.first_name = form.cleaned_data["first_name"]
            customer.last_name = form.cleaned_data["last_name"]
            new_email = form.cleaned_data["email"]
            new_username = form.cleaned_data["username"]
            if new_email != customer.email and User.objects.filter(email__iexact=new_email).exclude(id=user_id).exists():
                messages.error(request, "This email is already used by another account.")
            elif new_username != customer.username and User.objects.filter(username__iexact=new_username).exclude(id=user_id).exists():
                messages.error(request, "This username is already taken.")
            else:
                customer.email = new_email
                customer.username = new_username
                customer.save(update_fields=["first_name", "last_name", "email", "username"])
                messages.success(request, f"Updated account for {customer.username}.")
                return redirect("staff_customer_detail", user_id=user_id)
    else:
        form = CustomerEditForm(
            instance_user=customer,
            initial={
                "username": customer.username,
                "email": customer.email,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
            },
        )
    return render(request, "staff/customer_edit.html", {"customer": customer, "form": form})


@login_required(login_url="staff_login")
@user_passes_test(_is_staff_user, login_url="staff_login")
@require_POST
def staff_customer_toggle_active_view(request, user_id):
    customer = get_object_or_404(User, id=user_id, is_staff=False, is_superuser=False)
    customer.is_active = not customer.is_active
    customer.save(update_fields=["is_active"])
    status_label = "activated" if customer.is_active else "deactivated"
    messages.success(request, f"Account '{customer.username}' has been {status_label}.")
    return redirect("staff_customer_detail", user_id=user_id)


@login_required(login_url="staff_login")
@user_passes_test(_is_staff_user, login_url="staff_login")
@require_POST
def staff_customer_reset_password_view(request, user_id):
    customer = get_object_or_404(User, id=user_id, is_staff=False, is_superuser=False)
    alphabet = string.ascii_letters + string.digits
    temp_password = "".join(secrets.choice(alphabet) for _ in range(12))
    customer.set_password(temp_password)
    customer.save(update_fields=["password"])
    messages.success(
        request,
        f"Password reset for '{customer.username}'. Temporary password: {temp_password} — share this once only.",
    )
    return redirect("staff_customer_detail", user_id=user_id)
