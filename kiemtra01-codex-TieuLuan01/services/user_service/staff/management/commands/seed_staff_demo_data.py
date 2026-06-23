import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from customer.services import (
    add_to_cart,
    checkout_order,
    fetch_products,
    list_orders,
    pay_order,
    update_shipping_status,
)


User = get_user_model()

FIRST_NAMES = [
    "An",
    "Binh",
    "Chi",
    "Dung",
    "Giang",
    "Hanh",
    "Khanh",
    "Linh",
    "Minh",
    "Nam",
    "Ngoc",
    "Phuong",
    "Quang",
    "Thao",
    "Trang",
    "Vy",
]
LAST_NAMES = [
    "Nguyen",
    "Tran",
    "Le",
    "Pham",
    "Hoang",
    "Vu",
    "Vo",
    "Dang",
]
STREETS = [
    "Nguyen Hue",
    "Le Loi",
    "Tran Hung Dao",
    "Pham Ngu Lao",
    "Vo Van Tan",
    "Dien Bien Phu",
    "Hai Ba Trung",
]
CITIES = [
    ("Ho Chi Minh City", "700000"),
    ("Ha Noi", "100000"),
    ("Da Nang", "550000"),
    ("Can Tho", "900000"),
    ("Hai Phong", "180000"),
]
ORDER_LIFECYCLES = [
    {"payment": "paid", "shipping": "delivered"},
    {"payment": "paid", "shipping": "delivered"},
    {"payment": "paid", "shipping": "shipped"},
    {"payment": "paid", "shipping": "preparing"},
    {"payment": "paid", "shipping": "pending"},
    {"payment": "pending", "shipping": "pending"},
    {"payment": "pending", "shipping": "cancelled"},
]
SHIPPING_STEPS = {
    "pending": [],
    "preparing": ["preparing"],
    "shipped": ["preparing", "shipped"],
    "delivered": ["preparing", "shipped", "delivered"],
    "cancelled": ["cancelled"],
}


class Command(BaseCommand):
    help = "Create realistic synthetic customer and order data for the staff Customers and Orders screens."

    def add_arguments(self, parser):
        parser.add_argument("--customers", type=int, default=36, help="Number of synthetic customer accounts to maintain.")
        parser.add_argument("--min-orders", type=int, default=1, help="Minimum orders to create per customer without history.")
        parser.add_argument("--max-orders", type=int, default=4, help="Maximum orders to create per customer without history.")
        parser.add_argument("--seed", type=int, default=20260421, help="Random seed for deterministic synthetic data.")
        parser.add_argument("--prefix", default="demo_customer_", help="Username prefix for synthetic customer accounts.")
        parser.add_argument(
            "--force-orders",
            action="store_true",
            help="Create additional orders even when a synthetic customer already has existing order history.",
        )

    def _profile_for_index(self, index):
        first_name = FIRST_NAMES[(index - 1) % len(FIRST_NAMES)]
        last_name = LAST_NAMES[((index - 1) // len(FIRST_NAMES)) % len(LAST_NAMES)]
        city, postal_code = CITIES[(index - 1) % len(CITIES)]
        street = STREETS[(index - 1) % len(STREETS)]
        return {
            "username": f"{self.prefix}{index:03d}",
            "email": f"{self.prefix}{index:03d}@demo.local",
            "first_name": first_name,
            "last_name": last_name,
            "city": city,
            "postal_code": postal_code,
            "street": street,
            "phone": f"09{index:08d}"[-10:],
        }

    def _shipping_payload(self, profile, order_number):
        return {
            "recipient_name": f"{profile['last_name']} {profile['first_name']}",
            "phone": profile["phone"],
            "address_line": f"{100 + order_number} {profile['street']} Street",
            "city_or_region": profile["city"],
            "postal_code": profile["postal_code"],
            "country": "VN",
            "note": f"Synthetic staff demo order {order_number}",
        }

    def _create_or_update_customer(self, profile):
        user, created = User.objects.get_or_create(
            username=profile["username"],
            defaults={
                "email": profile["email"],
                "first_name": profile["first_name"],
                "last_name": profile["last_name"],
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        )
        updates = []
        for field in ("email", "first_name", "last_name"):
            value = profile[field]
            if getattr(user, field) != value:
                setattr(user, field, value)
                updates.append(field)
        for field, expected in (("is_staff", False), ("is_superuser", False), ("is_active", True)):
            if getattr(user, field) != expected:
                setattr(user, field, expected)
                updates.append(field)
        if created or not user.has_usable_password():
            user.set_password("demo12345")
            updates.append("password")
        if updates:
            user.save(update_fields=list(dict.fromkeys(updates)))
        return user, created

    def _product_payload(self, product, quantity):
        return {
            "category_slug": product["category_slug"],
            "category_name": product["category_name"],
            "product_id": product["id"],
            "product_name": product["name"],
            "product_brand": product["brand"],
            "product_image_url": product["image_url"],
            "unit_price": product["price"],
            "quantity": quantity,
            "stock": product["stock"],
        }

    def _advance_shipping(self, order_id, final_status):
        for status in SHIPPING_STEPS.get(final_status, []):
            ok, _, error = update_shipping_status(order_id, status)
            if not ok:
                raise CommandError(f"Unable to update shipping for order #{order_id} to '{status}': {error or 'unknown_error'}")

    def handle(self, *args, **options):
        customer_count = max(1, options["customers"])
        min_orders = max(1, options["min_orders"])
        max_orders = max(min_orders, options["max_orders"])
        self.prefix = str(options["prefix"] or "demo_customer_").strip()
        rng = random.Random(options["seed"])

        catalog = [product for product in fetch_products({"category": "all", "sort": "newest"}) if product.get("stock", 0) > 0]
        if len(catalog) < 8:
            raise CommandError("Synthetic seed requires at least 8 in-stock products from product_service.")

        created_users = 0
        reused_users = 0
        created_orders = 0
        skipped_users = 0

        synthetic_users = []
        for index in range(1, customer_count + 1):
            profile = self._profile_for_index(index)
            user, created = self._create_or_update_customer(profile)
            synthetic_users.append((user, profile))
            if created:
                created_users += 1
            else:
                reused_users += 1

        for user, profile in synthetic_users:
            existing_orders = list_orders(user.id)
            if existing_orders and not options["force_orders"]:
                skipped_users += 1
                continue

            order_target = rng.randint(min_orders, max_orders)
            for order_offset in range(1, order_target + 1):
                item_count = rng.randint(1, 3)
                for product in rng.sample(catalog, k=item_count):
                    quantity = rng.randint(1, 3)
                    ok, _, error = add_to_cart(user.id, self._product_payload(product, quantity))
                    if not ok:
                        raise CommandError(
                            f"Unable to add '{product['name']}' to cart for {user.username}: {error or 'unknown_error'}"
                        )

                ok, order, error = checkout_order(user.id, self._shipping_payload(profile, order_offset))
                if not ok or not order:
                    raise CommandError(f"Unable to checkout synthetic order for {user.username}: {error or 'unknown_error'}")
                created_orders += 1

                lifecycle = rng.choice(ORDER_LIFECYCLES)
                if lifecycle["payment"] == "paid":
                    ok, _, error = pay_order(user.id, order["id"])
                    if not ok:
                        raise CommandError(f"Unable to mark order #{order['id']} as paid: {error or 'unknown_error'}")
                self._advance_shipping(order["id"], lifecycle["shipping"])

        self.stdout.write(
            self.style.SUCCESS(
                "Synthetic staff demo seed complete. "
                f"Users created: {created_users}, reused: {reused_users}. "
                f"Orders created: {created_orders}. "
                f"Users skipped with existing orders: {skipped_users}."
            )
        )
