import csv
import html
import os
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from .category_taxonomy import category_items, category_name_from_slug, fetch_catalog_categories
from .dataset_generation import DATASET_PATH, load_catalog_products
from .rag_kb import ARTIFACT_DIR

DEMO_GRAPH_PATH = ARTIFACT_DIR / "behavior_graph_demo.svg"

BEHAVIOR_AFFINITY_WEIGHTS = {
    "search": Decimal("1.0"),
    "view_product": Decimal("1.6"),
    "chatbot_ask": Decimal("2.4"),
    "save_item": Decimal("3.0"),
    "compare_item": Decimal("3.2"),
    "add_to_cart": Decimal("4.2"),
    "checkout": Decimal("5.1"),
    "pay_order": Decimal("6.0"),
}

CONSTRAINT_QUERIES = [
    "CREATE CONSTRAINT user_user_ref IF NOT EXISTS FOR (u:User) REQUIRE u.user_ref IS UNIQUE",
    "CREATE CONSTRAINT behavior_behavior_id IF NOT EXISTS FOR (b:Behavior) REQUIRE b.behavior_id IS UNIQUE",
    "CREATE CONSTRAINT category_slug IF NOT EXISTS FOR (c:Category) REQUIRE c.slug IS UNIQUE",
    "CREATE CONSTRAINT product_product_id IF NOT EXISTS FOR (p:Product) REQUIRE p.product_id IS UNIQUE",
]

RESET_GRAPH_QUERY = """
MATCH (n)
WHERE n:User OR n:Behavior OR n:Category OR n:Product
DETACH DELETE n
"""

CATEGORY_IMPORT_QUERY = """
UNWIND $rows AS row
MERGE (c:Category {slug: row.slug})
SET c.name = row.name,
    c.category_slug = row.slug
"""

PRODUCT_IMPORT_QUERY = """
UNWIND $rows AS row
MATCH (c:Category {slug: row.category_slug})
MERGE (p:Product {product_id: row.product_id})
SET p.name = row.name,
    p.brand = row.brand,
    p.price = row.price,
    p.stock = row.stock,
    p.category_slug = row.category_slug,
    p.category_name = row.category_name,
    p.catalog_source = row.catalog_source
WITH p, c
OPTIONAL MATCH (p)-[old:BELONGS_TO]->(:Category)
FOREACH (rel IN CASE WHEN old IS NULL THEN [] ELSE [old] END | DELETE rel)
MERGE (p)-[:BELONGS_TO]->(c)
"""

USER_IMPORT_QUERY = """
UNWIND $rows AS row
MERGE (u:User {user_ref: row.user_ref})
SET u.event_count = row.event_count,
    u.session_count = row.session_count,
    u.primary_category_slug = row.primary_category_slug,
    u.primary_category_name = row.primary_category_name,
    u.affinity_total = row.affinity_total,
    u.last_event_ts = row.last_event_ts
"""

BEHAVIOR_IMPORT_QUERY = """
UNWIND $rows AS row
MATCH (u:User {user_ref: row.user_ref})
MATCH (c:Category {slug: row.category_slug})
MERGE (b:Behavior {behavior_id: row.behavior_id})
SET b.user_ref = row.user_ref,
    b.event_ts = row.event_ts,
    b.step_index = row.step_index,
    b.behavior_type = row.behavior_type,
    b.category_slug = row.category_slug,
    b.category_name = row.category_name,
    b.product_id = row.product_id,
    b.price_bucket = row.price_bucket,
    b.device_type = row.device_type,
    b.search_query = row.search_query,
    b.session_id = row.session_id,
    b.target_next_category_slug = row.target_next_category_slug,
    b.affinity_weight = row.affinity_weight
MERGE (u)-[:PERFORMED]->(b)
MERGE (b)-[:IN_CATEGORY]->(c)
FOREACH (_ IN CASE WHEN row.product_id > 0 THEN [1] ELSE [] END |
    MERGE (p:Product {product_id: row.product_id})
    ON CREATE SET
        p.name = row.product_name,
        p.brand = row.product_brand,
        p.price = row.product_price,
        p.stock = row.product_stock,
        p.category_slug = row.category_slug,
        p.category_name = row.category_name,
        p.catalog_source = row.catalog_source
    MERGE (b)-[:ON_PRODUCT]->(p)
)
"""

PREFERENCE_IMPORT_QUERY = """
UNWIND $rows AS row
MATCH (u:User {user_ref: row.user_ref})
MATCH (c:Category {slug: row.category_slug})
MERGE (u)-[pref:PREFERS]->(c)
SET pref.score = row.score,
    pref.share = row.share,
    pref.rank = row.rank,
    pref.event_count = row.event_count,
    pref.last_event_ts = row.last_event_ts
"""

DELETE_PREFERENCES_QUERY = "MATCH (:User)-[pref:PREFERS]->(:Category) DELETE pref"

GRAPH_CATEGORY_CONTEXT_QUERY = """
MATCH (c:Category {slug: $category_slug})
OPTIONAL MATCH (u:User {user_ref: $user_ref})-[pref:PREFERS]->(c)
OPTIONAL MATCH (u)-[:PERFORMED]->(b:Behavior)-[:IN_CATEGORY]->(c)
OPTIONAL MATCH (b)-[:ON_PRODUCT]->(p:Product)
WITH c, pref, b, p
ORDER BY b.event_ts DESC
RETURN
  c.slug AS category_slug,
  c.name AS category_name,
  coalesce(pref.score, 0.0) AS affinity_score,
  coalesce(pref.share, 0.0) AS affinity_share,
  collect(DISTINCT b.behavior_type)[0..$limit] AS recent_behaviors,
  collect(DISTINCT p {
    .product_id,
    .name,
    .brand,
    .price,
    .stock,
    .category_slug,
    .category_name
  })[0..$limit] AS related_products
LIMIT 1
"""

GRAPH_CURRENT_PRODUCT_QUERY = """
MATCH (p:Product {product_id: $product_id})-[:BELONGS_TO]->(c:Category)
OPTIONAL MATCH (u:User {user_ref: $user_ref})-[:PERFORMED]->(b:Behavior)-[:ON_PRODUCT]->(p)
WITH p, c, b
ORDER BY b.event_ts DESC
RETURN
  p.product_id AS product_id,
  p.name AS product_name,
  p.brand AS product_brand,
  p.price AS product_price,
  p.stock AS product_stock,
  c.slug AS category_slug,
  c.name AS category_name,
  collect(DISTINCT b.behavior_type)[0..6] AS recent_behaviors
LIMIT 1
"""


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal(default)


def _record_to_dict(record):
    if record is None:
        return {}
    if hasattr(record, "data") and callable(record.data):
        try:
            return record.data()
        except Exception:
            return {}
    try:
        return dict(record)
    except Exception:
        return {}


def _dashboard_url():
    return "/customer/dashboard/"


def _product_url(category_slug, product_id):
    if str(category_slug or "").strip() and _safe_int(product_id, 0) > 0:
        return f"/customer/products/{category_slug}/{int(product_id)}/"
    return _dashboard_url()


class BehaviorGraphRetriever:
    def __init__(self, uri=None, username=None, password=None, database=None, timeout_seconds=3):
        self.uri = str(uri or os.getenv("NEO4J_URI") or "bolt://neo4j:7687").strip()
        self.username = str(username or os.getenv("NEO4J_USERNAME") or "neo4j").strip()
        self.password = str(password or os.getenv("NEO4J_PASSWORD") or "graph_password").strip()
        self.database = str(database or os.getenv("NEO4J_DATABASE") or "neo4j").strip()
        self.timeout_seconds = max(1, int(timeout_seconds or 3))
        self._driver = None
        self._driver_error = None

    def _load_graph_database(self):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            self._driver_error = f"neo4j_driver_unavailable:{exc.__class__.__name__}"
            return None
        return GraphDatabase

    def _get_driver(self):
        if self._driver is not None or self._driver_error is not None:
            return self._driver
        GraphDatabase = self._load_graph_database()
        if GraphDatabase is None:
            return None
        try:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                connection_timeout=self.timeout_seconds,
                connection_acquisition_timeout=self.timeout_seconds,
            )
        except Exception as exc:
            self._driver_error = f"neo4j_connection_failed:{exc.__class__.__name__}"
            return None
        return self._driver

    def close(self):
        if self._driver is not None:
            close = getattr(self._driver, "close", None)
            if callable(close):
                close()
        self._driver = None

    def error(self):
        return self._driver_error

    def is_available(self):
        return self._get_driver() is not None

    def _run_single(self, query, params):
        driver = self._get_driver()
        if driver is None:
            return {}
        try:
            with driver.session(database=self.database) as session:
                record = session.run(query, **params).single()
        except Exception as exc:
            self._driver_error = f"neo4j_query_failed:{exc.__class__.__name__}"
            return {}
        return _record_to_dict(record)

    def fetch_context(self, *, user_ref="", category_slug="", current_product_id=0, limit=6):
        category_slug = str(category_slug or "").strip().lower()
        if not category_slug and _safe_int(current_product_id, 0) <= 0:
            return {
                "available": False,
                "status": "empty",
                "docs": [],
                "product_ids": [],
                "error": None,
            }

        category_row = {}
        if category_slug:
            category_row = self._run_single(
                GRAPH_CATEGORY_CONTEXT_QUERY,
                {
                    "user_ref": str(user_ref or "").strip(),
                    "category_slug": category_slug,
                    "limit": max(1, int(limit or 6)),
                },
            )
        product_row = {}
        if _safe_int(current_product_id, 0) > 0:
            product_row = self._run_single(
                GRAPH_CURRENT_PRODUCT_QUERY,
                {
                    "user_ref": str(user_ref or "").strip(),
                    "product_id": int(current_product_id),
                },
            )
            if category_slug and str(product_row.get("category_slug") or "").strip().lower() != category_slug:
                product_row = {}

        if self.error() and not category_row and not product_row:
            return {
                "available": False,
                "status": "unavailable",
                "docs": [],
                "product_ids": [],
                "error": self.error(),
            }

        docs = []
        product_ids = []

        if category_row:
            related_products = category_row.get("related_products") or []
            product_ids.extend(
                int(item.get("product_id") or 0)
                for item in related_products
                if isinstance(item, dict) and _safe_int(item.get("product_id"), 0) > 0
            )
            recent_behaviors = [str(item or "").strip() for item in (category_row.get("recent_behaviors") or []) if str(item or "").strip()]
            affinity_score = float(category_row.get("affinity_score") or 0.0)
            affinity_share = float(category_row.get("affinity_share") or 0.0)
            has_meaningful_graph_signal = bool(related_products or recent_behaviors or affinity_score > 0 or affinity_share > 0)
            behavior_text = ", ".join(recent_behaviors)
            product_labels = [
                f"{item.get('name') or 'N/A'} ({item.get('brand') or 'N/A'})"
                for item in related_products[:4]
                if isinstance(item, dict)
            ]
            if has_meaningful_graph_signal:
                docs.append(
                    {
                        "doc_id": f"graph:category:{category_row.get('category_slug') or category_slug}",
                        "doc_type": "graph",
                        "service": "neo4j",
                        "category_slug": category_row.get("category_slug") or category_slug,
                        "category_name": category_row.get("category_name") or category_name_from_slug(category_slug),
                        "product_id": 0,
                        "title": f"Behavior graph for {category_row.get('category_name') or category_name_from_slug(category_slug)}",
                        "text": (
                            f"Graph affinity score: {category_row.get('affinity_score') or 0}. "
                            f"Affinity share: {category_row.get('affinity_share') or 0}. "
                            f"Recent behaviors: {behavior_text or 'none'}. "
                            f"Graph-linked products: {', '.join(product_labels) if product_labels else 'none'}."
                        ),
                        "url": _dashboard_url(),
                    }
                )

        if product_row:
            product_id = _safe_int(product_row.get("product_id"), 0)
            if product_id > 0:
                product_ids.append(product_id)
            docs.append(
                {
                    "doc_id": f"graph:product:{product_id or 'current'}",
                    "doc_type": "graph",
                    "service": "neo4j",
                    "category_slug": product_row.get("category_slug") or category_slug,
                    "category_name": product_row.get("category_name") or category_name_from_slug(product_row.get("category_slug") or category_slug),
                    "product_id": product_id,
                    "title": product_row.get("product_name") or "Current graph product",
                    "text": (
                        f"Current product in graph: {product_row.get('product_name') or 'N/A'}. "
                        f"Brand: {product_row.get('product_brand') or 'N/A'}. "
                        f"Recent linked behaviors: {', '.join(product_row.get('recent_behaviors') or []) or 'none'}."
                    ),
                    "url": _product_url(product_row.get("category_slug") or category_slug, product_id),
                }
            )

        unique_product_ids = []
        seen = set()
        for product_id in product_ids:
            normalized = _safe_int(product_id, 0)
            if normalized <= 0 or normalized in seen:
                continue
            seen.add(normalized)
            unique_product_ids.append(normalized)

        return {
            "available": True,
            "status": "graph" if docs else "empty",
            "docs": docs,
            "product_ids": unique_product_ids,
            "error": self.error(),
        }


def _float_value(value):
    return float(_safe_decimal(value))


def _behavior_id(row):
    return f"{row['user_ref']}|{row['session_id']}|{row['step_index']}"


def _chunked(rows, batch_size):
    size = max(1, int(batch_size or 1))
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _product_rows_for_lookup():
    products, catalog_source = load_catalog_products()
    product_lookup = {}
    for product in products:
        product_lookup[int(product.product_id)] = {
            "product_id": int(product.product_id),
            "name": product.name,
            "brand": product.brand,
            "price": _float_value(product.price),
            "stock": int(product.stock),
            "category_slug": product.category_slug,
            "category_name": product.category_name,
            "catalog_source": catalog_source,
        }

    product_rows = sorted(product_lookup.values(), key=lambda item: item["product_id"])
    return product_lookup, product_rows, catalog_source


def _load_dataset_rows(dataset_path):
    path = Path(dataset_path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            normalized = {
                "user_ref": str(row.get("user_ref") or "").strip(),
                "event_ts": str(row.get("event_ts") or "").strip(),
                "step_index": _safe_int(row.get("step_index"), 0),
                "behavior_type": str(row.get("behavior_type") or "").strip(),
                "category_slug": str(row.get("category_slug") or "").strip().lower(),
                "product_id": _safe_int(row.get("product_id"), 0),
                "price_bucket": str(row.get("price_bucket") or "").strip().lower(),
                "device_type": str(row.get("device_type") or "").strip().lower(),
                "search_query": str(row.get("search_query") or "").strip(),
                "session_id": str(row.get("session_id") or "").strip(),
                "target_next_category_slug": str(row.get("target_next_category_slug") or "").strip().lower(),
            }
            if not normalized["user_ref"] or not normalized["behavior_type"] or not normalized["category_slug"]:
                continue
            normalized["behavior_id"] = _behavior_id(normalized)
            rows.append(normalized)
    rows.sort(key=lambda item: (item["user_ref"], item["session_id"], item["event_ts"], item["step_index"]))
    return rows


def build_behavior_graph_payload(
    *,
    dataset_path=None,
    preference_share_threshold=0.18,
    max_preferences_per_user=3,
):
    dataset_path = Path(dataset_path or DATASET_PATH)
    dataset_rows = _load_dataset_rows(dataset_path)
    dataset_slugs = sorted({row["category_slug"] for row in dataset_rows})
    categories = category_items(fetch_catalog_categories(), extra_slugs=dataset_slugs)
    category_lookup = {item["slug"]: item["name"] for item in categories}

    product_lookup, product_rows, catalog_source = _product_rows_for_lookup()
    referenced_product_ids = {row["product_id"] for row in dataset_rows if row["product_id"] > 0}
    missing_product_ids = sorted(product_id for product_id in referenced_product_ids if product_id not in product_lookup)
    if missing_product_ids:
        fallback_rows = []
        by_product = {}
        for row in dataset_rows:
            product_id = row["product_id"]
            if product_id <= 0 or product_id not in missing_product_ids or product_id in by_product:
                continue
            category_slug = row["category_slug"]
            by_product[product_id] = {
                "product_id": product_id,
                "name": f"{category_lookup.get(category_slug, category_slug.title())} Product {product_id}",
                "brand": "Unknown",
                "price": 0.0,
                "stock": 0,
                "category_slug": category_slug,
                "category_name": category_lookup.get(category_slug, category_name_from_slug(category_slug)),
                "catalog_source": "dataset_fallback",
            }
        fallback_rows = sorted(by_product.values(), key=lambda item: item["product_id"])
        product_rows.extend(fallback_rows)
        product_lookup.update({item["product_id"]: item for item in fallback_rows})

    user_scores = defaultdict(lambda: defaultdict(Decimal))
    user_category_events = defaultdict(Counter)
    user_event_counts = Counter()
    user_sessions = defaultdict(set)
    user_last_event = {}
    behavior_rows = []

    for row in dataset_rows:
        category_slug = row["category_slug"]
        category_name = category_lookup.get(category_slug, category_name_from_slug(category_slug))
        affinity_weight = BEHAVIOR_AFFINITY_WEIGHTS.get(row["behavior_type"], Decimal("1.0"))
        product = product_lookup.get(row["product_id"], {})

        user_scores[row["user_ref"]][category_slug] += affinity_weight
        user_category_events[row["user_ref"]][category_slug] += 1
        user_event_counts[row["user_ref"]] += 1
        if row["session_id"]:
            user_sessions[row["user_ref"]].add(row["session_id"])
        user_last_event[row["user_ref"]] = row["event_ts"]

        behavior_rows.append(
            {
                **row,
                "category_name": category_name,
                "affinity_weight": _float_value(affinity_weight),
                "product_name": product.get("name", ""),
                "product_brand": product.get("brand", ""),
                "product_price": float(product.get("price", 0.0)),
                "product_stock": int(product.get("stock", 0)),
                "catalog_source": product.get("catalog_source", catalog_source),
            }
        )

    user_rows = []
    preference_rows = []
    threshold = _safe_decimal(preference_share_threshold, "0.18")

    for user_ref in sorted(user_scores.keys()):
        ranked_scores = sorted(
            user_scores[user_ref].items(),
            key=lambda item: (-item[1], -user_category_events[user_ref][item[0]], item[0]),
        )
        total_affinity = sum(user_scores[user_ref].values(), Decimal("0"))
        primary_slug = ranked_scores[0][0] if ranked_scores else ""
        user_rows.append(
            {
                "user_ref": user_ref,
                "event_count": int(user_event_counts[user_ref]),
                "session_count": len(user_sessions[user_ref]),
                "primary_category_slug": primary_slug,
                "primary_category_name": category_lookup.get(primary_slug, category_name_from_slug(primary_slug)),
                "affinity_total": _float_value(total_affinity),
                "last_event_ts": user_last_event.get(user_ref, ""),
            }
        )

        kept_preferences = 0
        for rank, (category_slug, score) in enumerate(ranked_scores, start=1):
            share = (score / total_affinity) if total_affinity > 0 else Decimal("0")
            event_count = int(user_category_events[user_ref][category_slug])
            include_row = rank == 1 or (share >= threshold and event_count >= 2)
            if not include_row:
                continue
            preference_rows.append(
                {
                    "user_ref": user_ref,
                    "category_slug": category_slug,
                    "category_name": category_lookup.get(category_slug, category_name_from_slug(category_slug)),
                    "score": _float_value(score.quantize(Decimal("0.0001"))),
                    "share": _float_value(share.quantize(Decimal("0.0001"))),
                    "rank": kept_preferences + 1,
                    "event_count": event_count,
                    "last_event_ts": user_last_event.get(user_ref, ""),
                }
            )
            kept_preferences += 1
            if kept_preferences >= max(1, int(max_preferences_per_user or 1)):
                break

    return {
        "dataset_path": str(dataset_path),
        "categories": [
            {
                "slug": item["slug"],
                "name": item["name"],
            }
            for item in categories
        ],
        "products": sorted(product_rows, key=lambda item: item["product_id"]),
        "users": user_rows,
        "behaviors": behavior_rows,
        "preferences": preference_rows,
        "stats": {
            "user_count": len(user_rows),
            "behavior_count": len(behavior_rows),
            "category_count": len(categories),
            "product_count": len(product_rows),
            "preference_count": len(preference_rows),
            "catalog_source": catalog_source,
            "missing_product_count": len(missing_product_ids),
        },
    }


def sync_behavior_graph(session, payload, *, clear_existing=False, batch_size=250):
    for query in CONSTRAINT_QUERIES:
        session.run(query)

    if clear_existing:
        session.run(RESET_GRAPH_QUERY)
    else:
        session.run(DELETE_PREFERENCES_QUERY)

    session.run(CATEGORY_IMPORT_QUERY, rows=payload["categories"])

    for batch in _chunked(payload["products"], batch_size):
        session.run(PRODUCT_IMPORT_QUERY, rows=batch)
    for batch in _chunked(payload["users"], batch_size):
        session.run(USER_IMPORT_QUERY, rows=batch)
    for batch in _chunked(payload["behaviors"], batch_size):
        session.run(BEHAVIOR_IMPORT_QUERY, rows=batch)
    for batch in _chunked(payload["preferences"], batch_size):
        session.run(PREFERENCE_IMPORT_QUERY, rows=batch)

    return dict(payload["stats"])


def _demo_user(payload):
    preference_counter = Counter(row["user_ref"] for row in payload["preferences"])
    users = payload["users"]
    if not users:
        return None
    return max(
        users,
        key=lambda item: (
            preference_counter.get(item["user_ref"], 0),
            item.get("event_count", 0),
            item.get("user_ref", ""),
        ),
    )


def _svg_text(x, y, value, *, font_size=22, fill="#10203a", font_weight="500", anchor="start"):
    return (
        f'<text x="{x}" y="{y}" font-size="{font_size}" fill="{fill}" '
        f'font-family="Segoe UI, Arial, sans-serif" font-weight="{font_weight}" text-anchor="{anchor}">'
        f"{html.escape(str(value))}</text>"
    )


def write_behavior_graph_demo_svg(payload, output_path=DEMO_GRAPH_PATH):
    user = _demo_user(payload)
    if not user:
        return None

    user_ref = user["user_ref"]
    preferences = [row for row in payload["preferences"] if row["user_ref"] == user_ref]
    preferences.sort(key=lambda item: item["rank"])
    selected_categories = preferences[:3]
    selected_slugs = {row["category_slug"] for row in selected_categories}

    behaviors = [
        row
        for row in payload["behaviors"]
        if row["user_ref"] == user_ref and row["category_slug"] in selected_slugs
    ]
    behaviors.sort(key=lambda item: (item["event_ts"], item["step_index"]), reverse=True)
    selected_behaviors = behaviors[:6]

    product_ids = []
    for behavior in selected_behaviors:
        product_id = int(behavior["product_id"])
        if product_id > 0 and product_id not in product_ids:
            product_ids.append(product_id)
        if len(product_ids) >= 4:
            break
    product_lookup = {item["product_id"]: item for item in payload["products"]}
    selected_products = [product_lookup[product_id] for product_id in product_ids if product_id in product_lookup]

    width = 1680
    height = 1040
    category_positions = [
        (620, 180),
        (930, 120),
        (1240, 180),
    ]
    behavior_positions = [
        (720, 360),
        (910, 320),
        (1100, 360),
        (720, 560),
        (910, 600),
        (1100, 560),
    ]
    product_positions = [
        (1310, 330),
        (1310, 470),
        (1310, 610),
        (1310, 750),
    ]

    category_colors = ["#ffb84d", "#ff8f70", "#6cb6ff"]
    behavior_colors = {
        "search": "#7f8da6",
        "view_product": "#3d74b6",
        "chatbot_ask": "#4d8f5d",
        "save_item": "#8d5cf6",
        "compare_item": "#4ca6a8",
        "add_to_cart": "#ef8c32",
        "checkout": "#cc5d46",
        "pay_order": "#b73c54",
    }

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<linearGradient id="bg" x1="0%" x2="100%" y1="0%" y2="100%">',
        '<stop offset="0%" stop-color="#f7fafc" />',
        '<stop offset="100%" stop-color="#e6eef8" />',
        "</linearGradient>",
        '<filter id="shadow" x="-20%" y="-20%" width="160%" height="160%">',
        '<feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#97a6ba" flood-opacity="0.18" />',
        "</filter>",
        "</defs>",
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="url(#bg)" />',
        '<rect x="40" y="40" width="1600" height="960" rx="32" fill="#ffffff" filter="url(#shadow)" />',
        _svg_text(96, 110, "Neo4j Behavior Graph Demo", font_size=34, fill="#10203a", font_weight="700"),
        _svg_text(
            96,
            150,
            f"Dataset: {Path(payload['dataset_path']).name} | Users: {payload['stats']['user_count']} | Behaviors: {payload['stats']['behavior_count']}",
            font_size=18,
            fill="#52627a",
            font_weight="500",
        ),
    ]

    user_x = 260
    user_y = 500
    svg.append(f'<circle cx="{user_x}" cy="{user_y}" r="108" fill="#1c8f6f" />')
    svg.append(f'<circle cx="{user_x}" cy="{user_y}" r="132" fill="none" stroke="#d7f1ea" stroke-width="24" />')
    svg.append(_svg_text(user_x, user_y - 6, user_ref, font_size=28, fill="#ffffff", font_weight="700", anchor="middle"))
    svg.append(
        _svg_text(
            user_x,
            user_y + 34,
            f"{user['event_count']} events / {user['session_count']} sessions",
            font_size=18,
            fill="#dbfff5",
            anchor="middle",
        )
    )

    for index, category in enumerate(selected_categories):
        x, y = category_positions[index]
        color = category_colors[index % len(category_colors)]
        svg.append(f'<rect x="{x - 120}" y="{y - 44}" width="240" height="88" rx="26" fill="{color}" />')
        svg.append(_svg_text(x, y - 4, category["category_name"], font_size=22, fill="#17212d", font_weight="700", anchor="middle"))
        svg.append(
            _svg_text(
                x,
                y + 24,
                f"share {category['share']:.0%} | score {category['score']:.1f}",
                font_size=16,
                fill="#2a3545",
                font_weight="500",
                anchor="middle",
            )
        )
        svg.append(
            f'<path d="M {user_x + 116} {user_y - 40 + (index * 40)} C 380 {user_y - 140 + (index * 20)}, 460 {y + 10}, {x - 120} {y}" '
            f'fill="none" stroke="{color}" stroke-width="5" stroke-linecap="round" opacity="0.65" />'
        )
        svg.append(
            _svg_text(
                (user_x + x) / 2 - 20,
                user_y - 110 + (index * 26),
                "PREFERS",
                font_size=14,
                fill="#5a6b82",
                font_weight="700",
            )
        )

    for index, behavior in enumerate(selected_behaviors):
        x, y = behavior_positions[index]
        color = behavior_colors.get(behavior["behavior_type"], "#63748d")
        label = behavior["behavior_type"].replace("_", " ").title()
        svg.append(f'<circle cx="{x}" cy="{y}" r="42" fill="{color}" />')
        svg.append(_svg_text(x, y + 6, label, font_size=15, fill="#ffffff", font_weight="700", anchor="middle"))
        category_index = next(
            (position for position, category in enumerate(selected_categories) if category["category_slug"] == behavior["category_slug"]),
            0,
        )
        cx, cy = category_positions[category_index]
        svg.append(
            f'<path d="M {cx} {cy + 44} C {cx} {y - 60}, {x - 60} {y - 30}, {x - 42} {y}" '
            'fill="none" stroke="#c7d4e6" stroke-width="3.5" stroke-linecap="round" opacity="0.9" />'
        )
        svg.append(
            _svg_text(
                x - 28,
                y - 58,
                "IN_CATEGORY",
                font_size=13,
                fill="#657991",
                font_weight="700",
            )
        )
        svg.append(
            f'<path d="M {user_x + 108} {user_y + 8} C 450 {user_y + 30}, 540 {y + 30}, {x - 42} {y}" '
            'fill="none" stroke="#b8c7db" stroke-width="3" stroke-linecap="round" opacity="0.95" />'
        )

    for index, product in enumerate(selected_products):
        x, y = product_positions[index]
        svg.append(f'<rect x="{x}" y="{y}" width="260" height="104" rx="22" fill="#f4f8fd" stroke="#d6e0ee" stroke-width="2" />')
        svg.append(_svg_text(x + 22, y + 34, product["name"], font_size=20, fill="#13243d", font_weight="700"))
        svg.append(
            _svg_text(
                x + 22,
                y + 62,
                f"{product['brand']} | ${product['price']:.0f} | stock {product['stock']}",
                font_size=16,
                fill="#5a6d87",
            )
        )
        svg.append(
            _svg_text(
                x + 22,
                y + 86,
                category_name_from_slug(product["category_slug"]),
                font_size=15,
                fill="#4a8cc7",
                font_weight="700",
            )
        )

    for index, behavior in enumerate(selected_behaviors):
        product_id = int(behavior["product_id"])
        if product_id <= 0:
            continue
        try:
            product_index = next(i for i, product in enumerate(selected_products) if product["product_id"] == product_id)
        except StopIteration:
            continue
        bx, by = behavior_positions[index]
        px, py = product_positions[product_index]
        svg.append(
            f'<path d="M {bx + 42} {by} C {bx + 140} {by - 20}, {px - 60} {py + 24}, {px} {py + 48}" '
            'fill="none" stroke="#91a7c6" stroke-width="3.5" stroke-linecap="round" opacity="0.85" />'
        )
        svg.append(
            _svg_text(
                (bx + px) / 2 + 6,
                (by + py) / 2,
                "ON_PRODUCT",
                font_size=13,
                fill="#657991",
                font_weight="700",
            )
        )

    legend_items = [
        ("#1c8f6f", "User"),
        ("#ffb84d", "Category"),
        ("#3d74b6", "Behavior"),
        ("#f4f8fd", "Product"),
    ]
    for index, (color, label) in enumerate(legend_items):
        x = 120 + (index * 180)
        y = 880
        svg.append(f'<circle cx="{x}" cy="{y}" r="18" fill="{color}" stroke="#d0d8e5" stroke-width="1.5" />')
        svg.append(_svg_text(x + 32, y + 6, label, font_size=18, fill="#465b76", font_weight="600"))

    svg.append(
        _svg_text(
            96,
            945,
            "Layout highlights one user, top preferred categories, recent behaviors, and linked products for Phase 5 retrieval.",
            font_size=18,
            fill="#5f718a",
        )
    )
    svg.append("</svg>")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(svg), encoding="utf-8")
    return str(output_path)
