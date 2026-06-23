import os
import re
import time

import requests

FALLBACK_CATEGORIES = [
    {"slug": "business-laptops", "name": "Business Laptops"},
    {"slug": "gaming-laptops", "name": "Gaming Laptops"},
    {"slug": "ultrabooks", "name": "Ultrabooks"},
    {"slug": "smartphones", "name": "Smartphones"},
    {"slug": "tablets", "name": "Tablets"},
    {"slug": "smartwatches", "name": "Smartwatches"},
    {"slug": "audio", "name": "Audio"},
    {"slug": "keyboards-mice", "name": "Keyboards & Mice"},
    {"slug": "chargers-cables", "name": "Chargers & Cables"},
    {"slug": "bags-stands", "name": "Bags & Stands"},
]

CATEGORY_KEYWORDS = {
    "business-laptops": ["business laptop", "office laptop", "work laptop", "corporate laptop", "van phong"],
    "gaming-laptops": ["gaming laptop", "laptop gaming", "gpu laptop", "streaming laptop", "choi game"],
    "ultrabooks": ["ultrabook", "thin laptop", "light laptop", "portable laptop", "nhe"],
    "smartphones": ["smartphone", "phone", "dien thoai", "android", "iphone", "ios"],
    "tablets": ["tablet", "ipad", "tab", "may tinh bang"],
    "smartwatches": ["smartwatch", "watch", "dong ho", "wearable"],
    "audio": ["audio", "headphone", "earbud", "speaker", "microphone", "tai nghe", "loa", "mic"],
    "keyboards-mice": ["keyboard", "mouse", "ban phim", "chuot", "peripheral"],
    "chargers-cables": ["charger", "cable", "usb-c", "adapter", "dock", "sac", "cap"],
    "bags-stands": ["bag", "backpack", "stand", "sleeve", "pouch", "tui", "gia do"],
}

LEGACY_CATEGORY_GROUPS = {
    "laptop": {
        "slugs": {"business-laptops", "gaming-laptops", "ultrabooks"},
        "keywords": {"laptop", "notebook", "may tinh", "may tinh xach tay"},
    },
    "mobile": {
        "slugs": {"smartphones", "tablets", "smartwatches"},
        "keywords": {"mobile", "handheld", "thiet bi di dong"},
    },
    "accessory": {
        "slugs": {"audio", "keyboards-mice", "chargers-cables", "bags-stands"},
        "keywords": {"accessory", "accessories", "phu kien"},
    },
}

_CATEGORY_CACHE = {"expires_at": 0.0, "items": []}
_CATEGORY_CACHE_TTL_SECONDS = 60


def _product_service_url():
    return (os.getenv("PRODUCT_SERVICE_URL") or "http://product-service:8000").rstrip("/")


def _normalize_category(item):
    if not isinstance(item, dict):
        return None
    slug = str(item.get("slug") or "").strip().lower()
    if not slug:
        return None
    return {
        "slug": slug,
        "name": str(item.get("name") or slug.replace("-", " ").title()).strip()[:120],
    }


def category_items(categories=None, extra_slugs=None):
    normalized = []
    seen = set()
    for item in categories or FALLBACK_CATEGORIES:
        category = _normalize_category(item)
        if not category or category["slug"] in seen:
            continue
        seen.add(category["slug"])
        normalized.append(category)
    for slug in extra_slugs or []:
        normalized_slug = str(slug or "").strip().lower()
        if not normalized_slug or normalized_slug in seen:
            continue
        seen.add(normalized_slug)
        normalized.append({"slug": normalized_slug, "name": normalized_slug.replace("-", " ").title()})
    return normalized or [_normalize_category(item) for item in FALLBACK_CATEGORIES]


def fetch_catalog_categories(timeout=6, force_refresh=False):
    now = time.time()
    if not force_refresh and _CATEGORY_CACHE["items"] and _CATEGORY_CACHE["expires_at"] > now:
        return [dict(item) for item in _CATEGORY_CACHE["items"]]

    categories = []
    try:
        response = requests.get(f"{_product_service_url()}/api/categories/", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("results", payload) if isinstance(payload, dict) else payload
        if isinstance(items, list):
            categories = category_items(items)
    except (requests.RequestException, ValueError):
        categories = []

    categories = categories or category_items(FALLBACK_CATEGORIES)
    _CATEGORY_CACHE["items"] = [dict(item) for item in categories]
    _CATEGORY_CACHE["expires_at"] = now + _CATEGORY_CACHE_TTL_SECONDS
    return [dict(item) for item in categories]


def category_name_from_slug(slug, categories=None):
    normalized = str(slug or "").strip().lower()
    for item in category_items(categories):
        if item["slug"] == normalized:
            return item["name"]
    return normalized.replace("-", " ").title()


def category_slugs(categories=None, extra_slugs=None):
    return [item["slug"] for item in category_items(categories=categories, extra_slugs=extra_slugs)]


def _token_variants(text):
    variants = set()
    for token in re.findall(r"[a-z0-9]+", str(text or "").lower()):
        if len(token) <= 2:
            continue
        variants.add(token)
        if token.endswith("s") and len(token) > 4:
            variants.add(token[:-1])
    return variants


def _category_keywords(category):
    slug = str(category.get("slug") or "").strip().lower()
    name = str(category.get("name") or "").strip().lower()
    keywords = set(CATEGORY_KEYWORDS.get(slug, []))
    keywords.update(_token_variants(slug.replace("-", " ")))
    keywords.update(_token_variants(name))
    if name:
        keywords.add(name)
    for group in LEGACY_CATEGORY_GROUPS.values():
        if slug in group["slugs"]:
            keywords.update(group["keywords"])
    return {keyword.strip().lower() for keyword in keywords if keyword and len(keyword.strip()) > 2}


def detect_category_matches(text, categories=None):
    lowered = str(text or "").lower()
    matches = []
    for category in category_items(categories):
        slug = category["slug"]
        keywords = _category_keywords(category)
        if any(keyword in lowered for keyword in keywords):
            matches.append(slug)
    return matches
