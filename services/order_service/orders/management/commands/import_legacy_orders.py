from collections import defaultdict

try:
    import pymysql
except ModuleNotFoundError:
    pymysql = None
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from orders.models import Order, OrderItem, OrderShipping


def _mysql_connection(database_name):
    if pymysql is None:
        raise RuntimeError("PyMySQL is required to import legacy orders.")
    default_db = settings.DATABASES["default"]
    return pymysql.connect(
        host=default_db["HOST"],
        port=int(default_db["PORT"]),
        user=default_db["USER"],
        password=default_db["PASSWORD"],
        database=database_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _payment_status_from_legacy(status):
    normalized = str(status or "").strip().lower()
    if normalized == "paid":
        return Order.PAYMENT_PAID
    if normalized == "cancelled":
        return Order.PAYMENT_CANCELLED
    return Order.PAYMENT_PENDING


def _shipping_status_from_legacy(status):
    normalized = str(status or "").strip().lower()
    if normalized == "cancelled":
        return Order.SHIPPING_CANCELLED
    return Order.SHIPPING_PENDING


def _legacy_shipping_defaults():
    return {
        "recipient_name": "Legacy customer",
        "phone": "",
        "address_line": "",
        "city_or_region": "",
        "postal_code": "",
        "country": "",
        "note": "Imported from legacy customer_db without shipping snapshot.",
    }


class Command(BaseCommand):
    help = "Import legacy customer_service order history into order_service."

    def add_arguments(self, parser):
        parser.add_argument("--legacy-db", default="customer_db")
        parser.add_argument("--user-db", default=settings.DATABASES["default"]["NAME"].replace("order_db", "user_db"))
        parser.add_argument("--reset", action="store_true")

    def handle(self, *args, **options):
        if options["reset"]:
            deleted_orders, _ = Order.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted_orders} order rows before import."))

        legacy_db = options["legacy_db"]
        user_db = options["user_db"]

        with _mysql_connection(user_db) as user_conn:
            with user_conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT legacy_source, legacy_user_id, user_id
                    FROM customer_legacyusermapping
                    """
                )
                mapping_rows = cursor.fetchall()

        legacy_user_map = {
            (row["legacy_source"], int(row["legacy_user_id"])): int(row["user_id"])
            for row in mapping_rows
        }

        with _mysql_connection(legacy_db) as legacy_conn:
            with legacy_conn.cursor() as cursor:
                cursor.execute("SELECT * FROM customer_order ORDER BY id ASC")
                legacy_orders = cursor.fetchall()
                cursor.execute("SELECT * FROM customer_orderitem ORDER BY id ASC")
                legacy_items = cursor.fetchall()

        items_by_order = defaultdict(list)
        for item in legacy_items:
            items_by_order[int(item["order_id"])].append(item)

        imported = 0
        updated = 0
        skipped = 0
        for legacy_order in legacy_orders:
            mapped_user_id = legacy_user_map.get(("customer", int(legacy_order["user_id"])))
            if not mapped_user_id:
                skipped += 1
                continue

            legacy_order_id = int(legacy_order["id"])
            legacy_created_at = legacy_order["created_at"]
            payment_status = _payment_status_from_legacy(legacy_order["status"])
            paid_at = legacy_created_at if payment_status == Order.PAYMENT_PAID else None

            with transaction.atomic():
                order, created = Order.objects.update_or_create(
                    source=Order.SOURCE_LEGACY_IMPORT,
                    source_order_id=legacy_order_id,
                    defaults={
                        "user_id": mapped_user_id,
                        "total_amount": legacy_order["total_amount"],
                        "payment_status": payment_status,
                        "shipping_status": _shipping_status_from_legacy(legacy_order["status"]),
                    },
                )
                Order.objects.filter(id=order.id).update(
                    created_at=legacy_created_at,
                    updated_at=legacy_created_at,
                    paid_at=paid_at,
                )
                OrderShipping.objects.update_or_create(
                    order=order,
                    defaults=_legacy_shipping_defaults(),
                )
                order.items.all().delete()
                OrderItem.objects.bulk_create(
                    [
                        OrderItem(
                            order=order,
                            category_slug=str(item.get("product_service") or "").strip().lower(),
                            category_name=str(item.get("product_service") or "").strip().title(),
                            product_id=int(item.get("product_id") or 0),
                            product_name=item.get("product_name") or "",
                            product_brand=item.get("product_brand") or "",
                            product_image_url="",
                            unit_price=item.get("unit_price") or 0,
                            quantity=int(item.get("quantity") or 1),
                        )
                        for item in items_by_order.get(legacy_order_id, [])
                    ]
                )

            if created:
                imported += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Legacy order import finished. "
                f"imported={imported} updated={updated} skipped={skipped} total_now={Order.objects.count()}"
            )
        )
