# Phase 1 Shared Contract

This document freezes the shared contract that later phases must reuse as-is.

Scope:
- Freeze the official behavior vocabulary.
- Freeze the official category taxonomy used by ML and chatbot flows.
- Freeze the `data_user500.csv` schema and column semantics.
- Freeze the official artifact names for sequence-model training outputs.
- Freeze the current runtime contract shape of `/api/chat/reply/` and `/customer/chatbot/reply/`.

Non-goals:
- Do not change public routes.
- Do not change the current chatbot JSON shape.
- Do not add any behavior type beyond the 8 values listed here.

## 1. Official Behavior Types

The only allowed shared `behavior_type` values are:

1. `search`
2. `view_product`
3. `chatbot_ask`
4. `save_item`
5. `compare_item`
6. `add_to_cart`
7. `checkout`
8. `pay_order`

Rules:
- Spelling is exact and lowercase.
- No aliases are allowed in shared artifacts or datasets.
- `chatbot_ask` stays the canonical name because it already exists in the current chatbot runtime.

## 2. Official ML Label

The only official supervised-learning label name is:

- `target_next_category_slug`

Definition:
- It is the category slug of the next event in the same `(user_ref, session_id)` sequence after sorting by `event_ts`, then `step_index`.
- The label value must be one of the 10 official category slugs in Section 3.
- The final event in a session has no next event, so it must not be used as a supervised training row unless the pipeline explicitly drops rows with missing label targets.

## 3. Official Category Taxonomy

The official taxonomy is the existing catalog taxonomy in the repo, in catalog sort order:

1. `business-laptops`
2. `gaming-laptops`
3. `ultrabooks`
4. `smartphones`
5. `tablets`
6. `smartwatches`
7. `audio`
8. `keyboards-mice`
9. `chargers-cables`
10. `bags-stands`

Rules:
- These slugs are the only allowed category values for the ML label.
- Shared datasets and artifacts must preserve these exact strings.
- Do not reintroduce legacy group labels such as `laptop`, `mobile`, or `accessory` into shared ML data.

## 4. Official `data_user500.csv` Schema

Column order is fixed and must be exactly:

1. `user_ref`
2. `event_ts`
3. `step_index`
4. `behavior_type`
5. `category_slug`
6. `product_id`
7. `price_bucket`
8. `device_type`
9. `search_query`
10. `session_id`
11. `target_next_category_slug`

### 4.1 Row semantics

- One row represents one user behavior event.
- Rows must be sortable into a deterministic sequence by `(user_ref, session_id, event_ts, step_index)`.
- `step_index` is 1-based within a session.
- `event_ts` must be UTC in ISO 8601 format: `YYYY-MM-DDTHH:MM:SSZ`.

### 4.2 Column contract

`user_ref`
- Type: string
- Required: yes
- Meaning: stable user identifier used across services and training data
- Rule: preserve source IDs as strings; do not coerce to floating-point or add formatting

`event_ts`
- Type: string
- Required: yes
- Format: UTC ISO 8601, for example `2026-04-20T13:45:00Z`

`step_index`
- Type: integer
- Required: yes
- Rule: starts at `1` for the first event in a session and increments by `1`

`behavior_type`
- Type: string enum
- Required: yes
- Allowed values: the 8 values from Section 1 only

`category_slug`
- Type: string
- Required: yes
- Allowed values:
  - one of the 10 official category slugs
  - `""` only when the event is category-agnostic and cannot be deterministically resolved
- Resolution rules:
  - `view_product`, `save_item`, `compare_item`, `add_to_cart`: use the acted product category
  - `checkout`, `pay_order`: use the primary order category defined as the line item with the highest line total; tie-break by lower `product_id`
  - `search`, `chatbot_ask`: use the resolved category from the query/message if one official category is detected; otherwise allow `""`

`product_id`
- Type: integer
- Required: yes
- Rule:
  - use the acted product ID for product-level events
  - use the primary order item product ID for `checkout` and `pay_order`
  - use `0` when the event has no concrete product, such as category-wide search or generic chatbot queries

`price_bucket`
- Type: string enum
- Required: yes
- Allowed values:
  - `under_500`
  - `500_1000`
  - `1000_2000`
  - `above_2000`
  - `unknown`
- Rule:
  - bucket the acted product price or primary order item price
  - use `unknown` when there is no reliable product price for the event

`device_type`
- Type: string enum
- Required: yes
- Allowed values:
  - `desktop`
  - `mobile`
  - `tablet`
  - `unknown`
- Rule: if the source system cannot reliably provide device data, emit `unknown`

`search_query`
- Type: string
- Required: yes
- Rule:
  - for `search`, store the original search text
  - for `chatbot_ask`, store the original user message
  - for all other behaviors, store `""`

`session_id`
- Type: string
- Required: yes
- Meaning: opaque session identifier that groups rows into a single event sequence
- Rule: must be non-empty and stable for the duration of one user session

`target_next_category_slug`
- Type: string
- Required for supervised rows: yes
- Allowed values: one of the 10 official category slugs
- Rule:
  - compute from the next row in the same `(user_ref, session_id)` sequence
  - if there is no next row, the row is not a valid supervised training sample

### 4.3 CSV generation constraints

- The file name is fixed as `data_user500.csv`.
- The header row must match the exact column order above.
- Later phases must not add, remove, rename, or reorder columns.
- Later phases must not invent additional category slugs or behavior types.

## 5. Official Artifact Naming

These names are frozen for the sequence-model training outputs:

- `model_rnn.keras`
- `model_lstm.keras`
- `model_bilstm.keras`
- `model_best.keras`
- `metrics_comparison.csv`
- `confusion_matrix_rnn.png`
- `confusion_matrix_lstm.png`
- `confusion_matrix_bilstm.png`
- `history_rnn.png`
- `history_lstm.png`
- `history_bilstm.png`

Rules:
- Names are exact and case-sensitive.
- These artifacts must live under `services/chatbot_service/chatbot/artifacts/` unless a later phase explicitly adds a subdirectory without renaming the files.
- `model_best.keras` is the canonical deployable winner among the compared sequence models.
- These names do not rename or replace the current runtime artifacts already used by the chatbot service, such as `knowledge_base.json`, `model_behavior.json`, `training_data_behavior.json`, and `runtime_config.json`.

## 6. Official Runtime Contract

The public routes stay unchanged:

- `/api/chat/reply/`
- `/customer/chatbot/reply/`

### 6.1 `/api/chat/reply/`

Method:
- `POST`

Accepted request body:

```json
{
  "message": "string, required, max 500 chars after trimming",
  "current_product": {
    "category_slug": "string, optional",
    "category_name": "string, optional",
    "service": "string, optional alias of category_slug",
    "id": 123,
    "name": "string, optional",
    "brand": "string, optional",
    "price": "string, optional"
  },
  "user_context": {
    "cart_items": ["string"],
    "saved_items": ["string"],
    "recent_paid_items": ["string"]
  },
  "user_ref": "string, optional",
  "limit": 5
}
```

Success response shape for normal chat flow:

```json
{
  "answer": "string",
  "recommendations": [
    {
      "service": "string",
      "category_slug": "string",
      "category_name": "string",
      "id": 123,
      "name": "string",
      "brand": "string",
      "description": "string",
      "price": "string",
      "stock": 0,
      "image_url": "string"
    }
  ],
  "citations": [
    {
      "label": "string",
      "detail": "string",
      "url": "string"
    }
  ],
  "source": "string",
  "fallback_used": false,
  "error_code": null
}
```

Additional control-command success response:

```json
{
  "answer": "string",
  "recommendations": [],
  "citations": [],
  "source": "provider_control",
  "fallback_used": false,
  "error_code": null,
  "provider": "string"
}
```

Error response shape:

```json
{
  "error": "string"
}
```

Contract notes:
- Keep the response keys above unchanged.
- `provider` is currently only guaranteed on provider-control responses for this internal endpoint.
- `recommendations` and `citations` are arrays even when empty.

### 6.2 `/customer/chatbot/reply/`

Method:
- `POST`

Accepted request body from the web UI:

```json
{
  "message": "string, required, max 500 chars after trimming",
  "current_product": {
    "category_slug": "string, optional",
    "category_name": "string, optional",
    "id": 123,
    "name": "string, optional",
    "brand": "string, optional",
    "price": "string, optional"
  }
}
```

Success response shape:

```json
{
  "answer": "string",
  "recommendations": [
    {
      "service": "string",
      "category_slug": "string",
      "category_name": "string",
      "id": 123,
      "name": "string",
      "brand": "string",
      "price": "string",
      "stock": 0,
      "image_url": "string",
      "url": "string"
    }
  ],
  "citations": [
    {
      "label": "string",
      "detail": "string",
      "url": "string"
    }
  ],
  "source": "string",
  "fallback_used": false,
  "error_code": null,
  "provider": null
}
```

Error response shape:

```json
{
  "error": "string"
}
```

Contract notes:
- The proxy keeps the same top-level chat fields as today.
- The proxy normalizes recommendations to always include a customer-facing `url`.
- The proxy always includes `provider`, which may be `null`.
- Do not rename, remove, or reshape these fields in later phases.

## 7. Final Freeze Summary

The following are now closed decisions for later phases:

- Official behavior vocabulary: fixed to 8 values
- Official ML label name: fixed to `target_next_category_slug`
- Official category taxonomy: fixed to the 10 catalog slugs above
- Official CSV schema: fixed to 11 columns in fixed order
- Official artifact names: fixed to 11 file names above
- Official chatbot runtime response shapes: fixed for both routes above

Later phases must implement against this document rather than redefining enums, labels, slugs, CSV fields, or artifact names.
