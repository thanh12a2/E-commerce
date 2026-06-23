import csv
import json
import os
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

from .category_taxonomy import CATEGORY_KEYWORDS, category_items, category_name_from_slug, fetch_catalog_categories
from .rag_kb import ARTIFACT_DIR, KB_PATH

DATASET_COLUMNS = [
    "user_ref",
    "event_ts",
    "step_index",
    "behavior_type",
    "category_slug",
    "product_id",
    "price_bucket",
    "device_type",
    "search_query",
    "session_id",
    "target_next_category_slug",
]

OFFICIAL_BEHAVIOR_TYPES = [
    "search",
    "view_product",
    "chatbot_ask",
    "save_item",
    "compare_item",
    "add_to_cart",
    "checkout",
    "pay_order",
]

DATASET_PATH = ARTIFACT_DIR / "data_user500.csv"
DATASET_SAMPLE_PATH = ARTIFACT_DIR / "data_user500_sample20.csv"
DATASET_STATS_PATH = ARTIFACT_DIR / "dataset_stats.json"
DEFAULT_DATASET_SEED = 20260420

CATEGORY_POPULARITY = {
    "business-laptops": 0.11,
    "gaming-laptops": 0.09,
    "ultrabooks": 0.1,
    "smartphones": 0.17,
    "tablets": 0.08,
    "smartwatches": 0.07,
    "audio": 0.12,
    "keyboards-mice": 0.08,
    "chargers-cables": 0.1,
    "bags-stands": 0.08,
}

RELATED_CATEGORY_MAP = {
    "business-laptops": ["chargers-cables", "keyboards-mice", "bags-stands", "ultrabooks"],
    "gaming-laptops": ["audio", "keyboards-mice", "chargers-cables", "bags-stands"],
    "ultrabooks": ["bags-stands", "chargers-cables", "audio", "business-laptops"],
    "smartphones": ["smartwatches", "chargers-cables", "audio", "tablets"],
    "tablets": ["bags-stands", "audio", "chargers-cables", "smartphones"],
    "smartwatches": ["smartphones", "audio", "chargers-cables", "tablets"],
    "audio": ["smartphones", "gaming-laptops", "tablets", "smartwatches"],
    "keyboards-mice": ["business-laptops", "gaming-laptops", "ultrabooks", "tablets"],
    "chargers-cables": ["smartphones", "business-laptops", "tablets", "ultrabooks"],
    "bags-stands": ["ultrabooks", "business-laptops", "tablets", "smartphones"],
}

CATEGORY_INTENTS = {
    "business-laptops": ["office work", "hybrid meetings", "remote admin tasks", "finance spreadsheets"],
    "gaming-laptops": ["AAA gaming", "streaming setup", "esports travel", "video editing"],
    "ultrabooks": ["daily travel", "consulting work", "coffee shop writing", "light office work"],
    "smartphones": ["travel photos", "daily communication", "creator content", "battery life"],
    "tablets": ["note taking", "reading and media", "portable drawing", "study sessions"],
    "smartwatches": ["fitness tracking", "daily notifications", "running metrics", "sleep tracking"],
    "audio": ["commuting", "focus at work", "video calls", "music listening"],
    "keyboards-mice": ["home office", "desk comfort", "coding sessions", "gaming control"],
    "chargers-cables": ["travel charging", "desk setup", "fast charging", "multi device use"],
    "bags-stands": ["daily commute", "ergonomic desk", "business travel", "device protection"],
}

BUDGET_TEXT = {
    "under_500": ["budget", "under 500", "value pick"],
    "500_1000": ["mid range", "around 800", "good value"],
    "1000_2000": ["premium", "around 1500", "high performance"],
    "above_2000": ["top tier", "above 2000", "flagship"],
}

CATEGORY_DEVICE_WEIGHTS = {
    "business-laptops": {"desktop": 0.6, "mobile": 0.25, "tablet": 0.1, "unknown": 0.05},
    "gaming-laptops": {"desktop": 0.72, "mobile": 0.18, "tablet": 0.04, "unknown": 0.06},
    "ultrabooks": {"desktop": 0.42, "mobile": 0.38, "tablet": 0.12, "unknown": 0.08},
    "smartphones": {"desktop": 0.08, "mobile": 0.82, "tablet": 0.04, "unknown": 0.06},
    "tablets": {"desktop": 0.1, "mobile": 0.24, "tablet": 0.58, "unknown": 0.08},
    "smartwatches": {"desktop": 0.08, "mobile": 0.8, "tablet": 0.04, "unknown": 0.08},
    "audio": {"desktop": 0.38, "mobile": 0.44, "tablet": 0.08, "unknown": 0.1},
    "keyboards-mice": {"desktop": 0.76, "mobile": 0.1, "tablet": 0.05, "unknown": 0.09},
    "chargers-cables": {"desktop": 0.26, "mobile": 0.54, "tablet": 0.08, "unknown": 0.12},
    "bags-stands": {"desktop": 0.28, "mobile": 0.48, "tablet": 0.12, "unknown": 0.12},
}


@dataclass(frozen=True)
class CatalogProduct:
    product_id: int
    category_slug: str
    category_name: str
    name: str
    brand: str
    price: Decimal
    stock: int


def _product_service_url():
    return (os.getenv("PRODUCT_SERVICE_URL") or "http://product-service:8000").rstrip("/")


def _safe_decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _isoformat_z(value):
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _price_bucket(price):
    amount = _safe_decimal(price)
    if amount <= 0:
        return "unknown"
    if amount < 500:
        return "under_500"
    if amount < 1000:
        return "500_1000"
    if amount < 2000:
        return "1000_2000"
    return "above_2000"


def _sort_distribution(counter):
    return {
        key: counter[key]
        for key in sorted(counter.keys(), key=lambda item: (-counter[item], item))
    }


def _weighted_choice(rng, weights):
    items = list(weights.items())
    threshold = rng.random() * sum(weight for _, weight in items)
    cumulative = 0.0
    for value, weight in items:
        cumulative += weight
        if threshold <= cumulative:
            return value
    return items[-1][0]


def _fetch_catalog_products(timeout=6):
    try:
        response = requests.get(f"{_product_service_url()}/api/products/", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return []

    items = payload.get("results", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    categories = {item["slug"] for item in category_items(fetch_catalog_categories())}
    products = []
    for item in items:
        product_id = int(item.get("id") or 0)
        category_slug = str(item.get("category_slug") or "").strip().lower()
        if product_id <= 0 or category_slug not in categories:
            continue
        products.append(
            CatalogProduct(
                product_id=product_id,
                category_slug=category_slug,
                category_name=str(item.get("category_name") or category_name_from_slug(category_slug)),
                name=str(item.get("name") or f"{category_slug}-{product_id}"),
                brand=str(item.get("brand") or "Generic"),
                price=_safe_decimal(item.get("price") or "0"),
                stock=max(0, int(item.get("stock") or 0)),
            )
        )
    return sorted(products, key=lambda item: (item.category_slug, item.name, item.product_id))


def _products_from_knowledge_base():
    if not KB_PATH.exists():
        return []

    try:
        payload = json.loads(KB_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    documents = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(documents, list):
        return []

    categories = {item["slug"] for item in category_items(fetch_catalog_categories())}
    products = []
    for item in documents:
        if not isinstance(item, dict) or item.get("doc_type") != "product":
            continue
        category_slug = str(item.get("category_slug") or "").strip().lower()
        product_id = int(item.get("product_id") or 0)
        if category_slug not in categories or product_id <= 0:
            continue
        products.append(
            CatalogProduct(
                product_id=product_id,
                category_slug=category_slug,
                category_name=str(item.get("category_name") or category_name_from_slug(category_slug)),
                name=str(item.get("title") or f"{category_slug}-{product_id}"),
                brand=str(item.get("brand") or "Generic"),
                price=_safe_decimal(item.get("price") or "0"),
                stock=max(0, int(item.get("stock") or 0)),
            )
        )
    return sorted(products, key=lambda item: (item.category_slug, item.name, item.product_id))


def _synthetic_catalog(categories):
    price_points = {
        "business-laptops": [1049, 1199, 1399, 1599],
        "gaming-laptops": [1799, 1999, 2199, 2399],
        "ultrabooks": [949, 1099, 1249, 1499],
        "smartphones": [549, 799, 999, 1299],
        "tablets": [499, 679, 899, 1199],
        "smartwatches": [219, 329, 449, 699],
        "audio": [69, 149, 249, 329],
        "keyboards-mice": [59, 89, 119, 179],
        "chargers-cables": [19, 39, 69, 99],
        "bags-stands": [35, 59, 89, 189],
    }
    brands = {
        "business-laptops": ["Dell", "Lenovo", "HP", "ASUS"],
        "gaming-laptops": ["MSI", "ASUS", "Razer", "Acer"],
        "ultrabooks": ["ASUS", "Dell", "Lenovo", "HP"],
        "smartphones": ["Apple", "Samsung", "Google", "OnePlus"],
        "tablets": ["Apple", "Samsung", "Microsoft", "Xiaomi"],
        "smartwatches": ["Apple", "Samsung", "Garmin", "Amazfit"],
        "audio": ["Sony", "Apple", "HyperX", "Google"],
        "keyboards-mice": ["Keychron", "Logitech", "Razer", "Microsoft"],
        "chargers-cables": ["Anker", "Belkin", "UGREEN", "Mophie"],
        "bags-stands": ["Peak Design", "Tomtoc", "MOFT", "Native Union"],
    }

    synthetic = []
    base_product_id = 9000
    for category_index, category in enumerate(categories, start=1):
        slug = category["slug"]
        names = [
            f"{category['name']} Core {index}"
            for index in range(1, 5)
        ]
        for product_index, (name, brand, price) in enumerate(zip(names, brands[slug], price_points[slug]), start=1):
            synthetic.append(
                CatalogProduct(
                    product_id=base_product_id + (category_index * 10) + product_index,
                    category_slug=slug,
                    category_name=category["name"],
                    name=name,
                    brand=brand,
                    price=Decimal(str(price)),
                    stock=20 + product_index,
                )
            )
    return synthetic


def load_catalog_products():
    products = _fetch_catalog_products()
    if products:
        return products, "product_service"

    products = _products_from_knowledge_base()
    if products:
        return products, "knowledge_base"

    categories = category_items(fetch_catalog_categories())
    return _synthetic_catalog(categories), "synthetic_fallback"


def _index_products(products):
    grouped = defaultdict(list)
    bucketed = defaultdict(lambda: defaultdict(list))
    for product in products:
        grouped[product.category_slug].append(product)
        bucketed[product.category_slug][_price_bucket(product.price)].append(product)
    return grouped, bucketed


def _profile_category_weights(primary_slug, secondary_slug, tertiary_slug, all_slugs):
    weights = {slug: 0.03 for slug in all_slugs}
    weights[primary_slug] = 0.58
    weights[secondary_slug] = 0.24
    weights[tertiary_slug] = 0.1
    return weights


def _build_user_profiles(user_count, categories, rng):
    all_slugs = [item["slug"] for item in categories]
    profiles = []
    for user_index in range(1, user_count + 1):
        primary_slug = _weighted_choice(rng, CATEGORY_POPULARITY)
        related = [slug for slug in RELATED_CATEGORY_MAP.get(primary_slug, []) if slug != primary_slug]
        secondary_slug = related[0] if related else rng.choice([slug for slug in all_slugs if slug != primary_slug])
        tertiary_candidates = [slug for slug in all_slugs if slug not in {primary_slug, secondary_slug}]
        tertiary_slug = rng.choice(tertiary_candidates)
        device_weights = dict(CATEGORY_DEVICE_WEIGHTS[primary_slug])
        session_count = rng.randint(4, 7)
        profiles.append(
            {
                "user_ref": f"user_{user_index:04d}",
                "session_count": session_count,
                "primary_slug": primary_slug,
                "secondary_slug": secondary_slug,
                "tertiary_slug": tertiary_slug,
                "category_weights": _profile_category_weights(
                    primary_slug=primary_slug,
                    secondary_slug=secondary_slug,
                    tertiary_slug=tertiary_slug,
                    all_slugs=all_slugs,
                ),
                "device_weights": device_weights,
            }
        )
    return profiles


def _pick_product(category_slug, grouped_products, bucketed_products, rng, preferred_bucket=None, exclude_ids=None):
    exclude_ids = set(exclude_ids or [])
    if preferred_bucket and bucketed_products[category_slug].get(preferred_bucket):
        candidates = [
            product for product in bucketed_products[category_slug][preferred_bucket] if product.product_id not in exclude_ids
        ]
        if candidates:
            return rng.choice(candidates)

    candidates = [product for product in grouped_products[category_slug] if product.product_id not in exclude_ids]
    if not candidates:
        candidates = list(grouped_products[category_slug])
    return rng.choice(candidates)


def _pick_session_category(profile, rng):
    return _weighted_choice(rng, profile["category_weights"])


def _pick_device_type(profile, session_category, rng):
    base_weights = dict(profile["device_weights"])
    category_weights = CATEGORY_DEVICE_WEIGHTS[session_category]
    blended = {}
    for device_type in ["desktop", "mobile", "tablet", "unknown"]:
        blended[device_type] = round((base_weights.get(device_type, 0) * 0.55) + (category_weights.get(device_type, 0) * 0.45), 6)
    return _weighted_choice(rng, blended)


def _flow_weights(session_category):
    if session_category in {"business-laptops", "gaming-laptops", "smartphones"}:
        return {"purchase": 0.48, "save": 0.18, "compare": 0.18, "chatbot": 0.16}
    if session_category in {"audio", "chargers-cables", "bags-stands"}:
        return {"purchase": 0.42, "save": 0.22, "compare": 0.12, "chatbot": 0.24}
    return {"purchase": 0.4, "save": 0.2, "compare": 0.18, "chatbot": 0.22}


def _budget_preference_for_product(product):
    bucket = _price_bucket(product.price)
    if bucket == "1000_2000":
        return {"1000_2000": 0.64, "500_1000": 0.14, "above_2000": 0.16, "under_500": 0.06}
    if bucket == "above_2000":
        return {"above_2000": 0.74, "1000_2000": 0.18, "500_1000": 0.05, "under_500": 0.03}
    if bucket == "500_1000":
        return {"500_1000": 0.61, "under_500": 0.18, "1000_2000": 0.18, "above_2000": 0.03}
    return {"under_500": 0.68, "500_1000": 0.2, "1000_2000": 0.08, "above_2000": 0.04}


def _search_phrase(category_slug, product, budget_bucket, rng):
    keyword_options = CATEGORY_KEYWORDS.get(category_slug) or [category_slug.replace("-", " ")]
    intent = rng.choice(CATEGORY_INTENTS.get(category_slug) or ["daily use"])
    budget_hint = rng.choice(BUDGET_TEXT.get(budget_bucket) or ["good value"])
    phrase_templates = [
        f"{rng.choice(keyword_options)} for {intent}",
        f"{budget_hint} {rng.choice(keyword_options)}",
        f"{product.brand} {rng.choice(keyword_options)} for {intent}",
        f"best {rng.choice(keyword_options)} {budget_hint}",
    ]
    return rng.choice(phrase_templates)[:120]


def _chatbot_message(category_slug, product, rng):
    intent = rng.choice(CATEGORY_INTENTS.get(category_slug) or ["daily use"])
    messages = [
        f"Is {product.name} a good pick for {intent}?",
        f"Can you compare {product.name} with similar {category_slug.replace('-', ' ')}?",
        f"What should I know before buying {product.brand} {product.name}?",
        f"Would {product.name} work well for {intent} and travel?",
    ]
    return rng.choice(messages)[:180]


def _build_row(
    *,
    user_ref,
    event_ts,
    step_index,
    behavior_type,
    category_slug,
    product_id,
    price_bucket,
    device_type,
    search_query,
    session_id,
):
    return {
        "user_ref": user_ref,
        "event_ts": _isoformat_z(event_ts),
        "step_index": step_index,
        "behavior_type": behavior_type,
        "category_slug": category_slug,
        "product_id": int(product_id),
        "price_bucket": price_bucket,
        "device_type": device_type,
        "search_query": search_query,
        "session_id": session_id,
        "target_next_category_slug": "",
    }


def _finalize_targets(rows):
    for index, row in enumerate(rows):
        next_slug = rows[index + 1]["category_slug"] if index + 1 < len(rows) else ""
        row["target_next_category_slug"] = next_slug
    return rows


def _session_rows(
    *,
    user_ref,
    session_id,
    session_category,
    session_start,
    flow_type,
    primary_product,
    secondary_product,
    device_type,
    rng,
):
    rows = []
    step_index = 1
    current_ts = session_start
    search_query = _search_phrase(session_category, primary_product, _price_bucket(primary_product.price), rng)

    def add_event(behavior_type, category_slug, product, query_text=""):
        nonlocal step_index, current_ts
        rows.append(
            _build_row(
                user_ref=user_ref,
                event_ts=current_ts,
                step_index=step_index,
                behavior_type=behavior_type,
                category_slug=category_slug,
                product_id=product.product_id if product else 0,
                price_bucket=_price_bucket(product.price) if product else "unknown",
                device_type=device_type,
                search_query=query_text,
                session_id=session_id,
            )
        )
        step_index += 1
        current_ts += timedelta(minutes=rng.randint(1, 8), seconds=rng.randint(0, 45))

    add_event("search", session_category, None, search_query)

    if rng.random() < 0.08:
        refined_query = f"{search_query} {rng.choice(['review', 'sale', 'battery', 'best'])}"[:120]
        add_event("search", session_category, None, refined_query)

    add_event("view_product", primary_product.category_slug, primary_product)

    if flow_type in {"save", "compare", "chatbot"} and rng.random() < 0.22:
        add_event("view_product", secondary_product.category_slug, secondary_product)

    if flow_type == "purchase":
        accessory_product = None
        if primary_product.category_slug not in {"audio", "keyboards-mice", "chargers-cables", "bags-stands"} and rng.random() < 0.18:
            related_slug = rng.choice(RELATED_CATEGORY_MAP.get(primary_product.category_slug) or [primary_product.category_slug])
            if related_slug != primary_product.category_slug:
                accessory_product = secondary_product if secondary_product.category_slug == related_slug else None
        add_event("add_to_cart", primary_product.category_slug, primary_product)
        if accessory_product:
            add_event("add_to_cart", accessory_product.category_slug, accessory_product)
        primary_order_product = primary_product
        if accessory_product and accessory_product.price > primary_product.price:
            primary_order_product = accessory_product
        add_event("checkout", primary_order_product.category_slug, primary_order_product)
        add_event("pay_order", primary_order_product.category_slug, primary_order_product)
    elif flow_type == "save":
        add_event("save_item", primary_product.category_slug, primary_product)
    elif flow_type == "compare":
        add_event("compare_item", secondary_product.category_slug, secondary_product)
    else:
        add_event("chatbot_ask", primary_product.category_slug, primary_product, _chatbot_message(primary_product.category_slug, primary_product, rng))

    return _finalize_targets(rows)


def _sample_rows(rows, sample_size):
    if len(rows) <= sample_size:
        return list(rows)
    indexes = []
    for index in range(sample_size):
        ratio = index / max(1, sample_size - 1)
        indexes.append(int(round(ratio * (len(rows) - 1))))
    deduped_indexes = []
    seen = set()
    for index in indexes:
        if index not in seen:
            seen.add(index)
            deduped_indexes.append(index)
    while len(deduped_indexes) < sample_size:
        candidate = deduped_indexes[-1] + 1
        if candidate >= len(rows):
            break
        deduped_indexes.append(candidate)
    return [rows[index] for index in deduped_indexes[:sample_size]]


def build_behavior_dataset(*, user_count=500, seed=DEFAULT_DATASET_SEED):
    rng = random.Random(seed)
    categories = category_items(fetch_catalog_categories())
    allowed_slugs = [item["slug"] for item in categories]
    products, catalog_source = load_catalog_products()
    grouped_products, bucketed_products = _index_products(products)

    for slug in allowed_slugs:
        if not grouped_products.get(slug):
            fallback_product = _synthetic_catalog(categories)
            grouped_products, bucketed_products = _index_products(fallback_product)
            catalog_source = "synthetic_fallback"
            break

    profiles = _build_user_profiles(user_count, categories, rng)
    base_datetime = datetime(2026, 1, 3, 2, 0, tzinfo=timezone.utc)
    all_rows = []

    for user_position, profile in enumerate(profiles, start=1):
        last_session_start = base_datetime + timedelta(days=(user_position - 1) % 28, minutes=user_position * 7)
        for session_number in range(1, profile["session_count"] + 1):
            last_session_start += timedelta(days=rng.randint(2, 9), hours=rng.randint(0, 6), minutes=rng.randint(10, 120))
            session_category = _pick_session_category(profile, rng)
            flow_type = _weighted_choice(rng, _flow_weights(session_category))
            session_device = _pick_device_type(profile, session_category, rng)
            session_id = f"{profile['user_ref']}_sess_{session_number:02d}"

            seed_product = _pick_product(
                category_slug=session_category,
                grouped_products=grouped_products,
                bucketed_products=bucketed_products,
                rng=rng,
                preferred_bucket=_weighted_choice(rng, _budget_preference_for_product(rng.choice(grouped_products[session_category]))),
                exclude_ids=None,
            )
            compare_slug = session_category
            if flow_type == "purchase" and rng.random() < 0.12:
                compare_slug = rng.choice(RELATED_CATEGORY_MAP.get(session_category) or [session_category])
            secondary_product = _pick_product(
                category_slug=compare_slug if compare_slug in grouped_products else session_category,
                grouped_products=grouped_products,
                bucketed_products=bucketed_products,
                rng=rng,
                preferred_bucket=None,
                exclude_ids={seed_product.product_id},
            )

            session_rows = _session_rows(
                user_ref=profile["user_ref"],
                session_id=session_id,
                session_category=session_category,
                session_start=last_session_start,
                flow_type=flow_type,
                primary_product=seed_product,
                secondary_product=secondary_product,
                device_type=session_device,
                rng=rng,
            )
            all_rows.extend(session_rows)

    all_rows.sort(key=lambda row: (row["user_ref"], row["session_id"], row["event_ts"], row["step_index"]))

    behavior_counter = Counter(row["behavior_type"] for row in all_rows)
    category_counter = Counter(row["category_slug"] for row in all_rows)
    device_counter = Counter(row["device_type"] for row in all_rows)
    price_bucket_counter = Counter(row["price_bucket"] for row in all_rows)
    session_lengths = Counter(row["session_id"] for row in all_rows)
    sessions_by_user = defaultdict(set)
    for row in all_rows:
        sessions_by_user[row["user_ref"]].add(row["session_id"])
    distinct_session_ids = sorted({row["session_id"] for row in all_rows})
    distinct_products = sorted({row["product_id"] for row in all_rows if int(row["product_id"]) > 0})

    stats = {
        "user_count": len({row["user_ref"] for row in all_rows}),
        "event_count": len(all_rows),
        "session_count": len(distinct_session_ids),
        "behavior_distribution": _sort_distribution(behavior_counter),
        "category_distribution": _sort_distribution(category_counter),
        "device_type_distribution": _sort_distribution(device_counter),
        "price_bucket_distribution": _sort_distribution(price_bucket_counter),
        "supervised_row_count": sum(1 for row in all_rows if row["target_next_category_slug"]),
        "terminal_row_count": sum(1 for row in all_rows if not row["target_next_category_slug"]),
        "avg_events_per_session": round(len(all_rows) / max(1, len(distinct_session_ids)), 2),
        "avg_sessions_per_user": round(len(distinct_session_ids) / max(1, user_count), 2),
        "min_sessions_per_user": min((len(session_ids) for session_ids in sessions_by_user.values()), default=0),
        "max_sessions_per_user": max((len(session_ids) for session_ids in sessions_by_user.values()), default=0),
        "max_session_length": max(session_lengths.values()) if session_lengths else 0,
        "unique_product_count": len(distinct_products),
        "catalog_source": catalog_source,
        "seed": seed,
    }

    return all_rows, _sample_rows(all_rows, 20), stats


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DATASET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_behavior_dataset_bundle(*, output_dir=None, user_count=500, sample_size=20, seed=DEFAULT_DATASET_SEED):
    output_dir = Path(output_dir) if output_dir else ARTIFACT_DIR
    rows, sample_rows, stats = build_behavior_dataset(user_count=user_count, seed=seed)
    sample_rows = _sample_rows(rows, sample_size)

    dataset_path = output_dir / DATASET_PATH.name
    sample_path = output_dir / DATASET_SAMPLE_PATH.name
    stats_path = output_dir / DATASET_STATS_PATH.name

    _write_csv(dataset_path, rows)
    _write_csv(sample_path, sample_rows)
    stats_path.write_text(json.dumps(stats, ensure_ascii=True, indent=2), encoding="utf-8")

    return {
        "dataset_path": dataset_path,
        "sample_path": sample_path,
        "stats_path": stats_path,
        "stats": stats,
    }
