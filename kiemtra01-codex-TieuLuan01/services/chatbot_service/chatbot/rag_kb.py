import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests

from .category_taxonomy import category_items, category_name_from_slug, fetch_catalog_categories
from .content import FAQ_ITEMS

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
KB_PATH = ARTIFACT_DIR / "knowledge_base.json"


def _product_service_url():
    return (os.getenv("PRODUCT_SERVICE_URL") or "http://product-service:8000").rstrip("/")


def _tokenize(text):
    return [token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(token) > 1]


def _ensure_artifact_dir():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _fetch_products(limit=120):
    try:
        response = requests.get(f"{_product_service_url()}/api/products/", timeout=6)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return []

    items = payload.get("results", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    categories = fetch_catalog_categories()
    docs = []
    for item in items[: max(1, limit)]:
        product_id = int(item.get("id") or 0)
        if product_id <= 0:
            continue
        category_slug = str(item.get("category_slug") or "").strip().lower()
        category_name = item.get("category_name") or category_name_from_slug(category_slug, categories=categories)
        docs.append(
            {
                "doc_id": f"product:{category_slug}:{product_id}",
                "doc_type": "product",
                "service": category_slug,
                "category_slug": category_slug,
                "category_name": category_name,
                "product_id": product_id,
                "title": item.get("name") or "N/A",
                "text": (
                    f"{item.get('name') or 'N/A'}. Category: {category_name}. Brand: {item.get('brand') or ''}. "
                    f"Price: {item.get('price') or '0'}. Stock: {item.get('stock') or 0}. "
                    f"Description: {item.get('description') or ''}"
                ),
                "url": f"/customer/products/{category_slug}/{product_id}/",
                "brand": item.get("brand") or "",
                "price": str(item.get("price") or "0"),
                "stock": int(item.get("stock") or 0),
            }
        )
    return docs


def _faq_docs():
    docs = []
    for index, item in enumerate(FAQ_ITEMS, start=1):
        docs.append(
            {
                "doc_id": f"faq:{index}",
                "doc_type": "faq",
                "service": "",
                "category_slug": "",
                "category_name": "",
                "product_id": 0,
                "title": item.get("question") or f"FAQ {index}",
                "text": f"Q: {item.get('question')}. A: {item.get('answer')}",
                "url": "/customer/dashboard/#section-faq",
            }
        )
    return docs


def build_and_save_knowledge_base(max_products=120):
    categories = category_items(fetch_catalog_categories())
    docs = _faq_docs()
    docs.extend(_fetch_products(limit=max_products))
    for doc in docs:
        doc["tokens"] = _tokenize(f"{doc.get('title') or ''} {doc.get('text') or ''}")

    payload = {
        "version": 3,
        "categories": categories,
        "documents": docs,
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "stats": {
            "total_docs": len(docs),
            "product_docs": len([doc for doc in docs if doc.get("doc_type") == "product"]),
            "faq_docs": len([doc for doc in docs if doc.get("doc_type") == "faq"]),
            "category_count": len(categories),
        },
    }
    _ensure_artifact_dir()
    KB_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return payload


def _is_valid_kb_payload(payload):
    if not isinstance(payload, dict):
        return False
    if int(payload.get("version") or 0) < 3:
        return False
    if not isinstance(payload.get("categories"), list):
        return False
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return False
    for doc in documents:
        if not isinstance(doc, dict):
            return False
        if doc.get("doc_type") == "product" and not str(doc.get("category_slug") or "").strip().lower():
            return False
    return True


def load_knowledge_base(auto_build=True):
    if KB_PATH.exists():
        try:
            payload = json.loads(KB_PATH.read_text(encoding="utf-8"))
            if _is_valid_kb_payload(payload):
                return payload
        except (OSError, ValueError):
            pass

    if auto_build:
        return build_and_save_knowledge_base()
    return {"version": 3, "categories": category_items(fetch_catalog_categories()), "documents": [], "stats": {}}


def _score_document(doc, question_tokens, preferred_categories=None, current_product=None):
    preferred_categories = preferred_categories or []
    token_set = set(doc.get("tokens") or [])
    if not token_set:
        return -999.0

    overlap = sum(1 for token in question_tokens if token in token_set)
    score = min(6.0, overlap * 1.2)

    if doc.get("doc_type") == "product":
        category_slug = str(doc.get("category_slug") or "").strip().lower()
        if category_slug in preferred_categories:
            score += 2.0
        if int(doc.get("stock") or 0) > 0:
            score += 0.8
        else:
            score -= 1.0
        if category_slug == str((current_product or {}).get("category_slug") or "").strip().lower():
            score += 0.6
        if int(doc.get("product_id") or 0) == int((current_product or {}).get("id") or 0):
            score -= 2.0
    else:
        score += 0.4

    return score


def retrieve_rag_context(question, preferred_categories=None, current_product=None, top_k=6):
    payload = load_knowledge_base(auto_build=True)
    docs = payload.get("documents") or []
    question_tokens = _tokenize(question)
    ranked = [
        (
            _score_document(
                doc,
                question_tokens=question_tokens,
                preferred_categories=preferred_categories,
                current_product=current_product,
            ),
            doc,
        )
        for doc in docs
    ]
    ranked.sort(key=lambda row: row[0], reverse=True)

    selected = []
    seen = set()
    for _, doc in ranked:
        doc_id = doc.get("doc_id")
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        selected.append(doc)
        if len(selected) >= max(1, top_k):
            break
    return selected


def rag_citations_from_docs(docs, limit=3):
    citations = []
    for doc in docs:
        if len(citations) >= max(1, limit):
            break
        if doc.get("doc_type") == "product":
            detail = f"[{doc.get('category_slug')}] {doc.get('title') or 'N/A'}"
            label = "Product catalog"
        elif doc.get("doc_type") == "graph":
            detail = doc.get("title") or "Behavior graph"
            label = "Behavior graph"
        else:
            detail = doc.get("title") or "FAQ"
            label = "FAQ"
        citations.append({"label": label, "detail": detail, "url": doc.get("url") or "/customer/dashboard/"})
    return citations
