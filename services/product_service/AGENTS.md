# AGENTS.md

## Project overview
This service is the unified Django REST catalog API. It owns `Category` and `Product`, seeds the 10-category taxonomy, exposes `/api/categories/` and `/api/products/`, and protects write operations with `X-Staff-Key`.

## Goals
- Keep category/product contracts stable for `user_service` and `chatbot_service`.
- Prefer schema clarity and deterministic seed data over ad-hoc compatibility hacks.

## Coding rules
- Keep the unified taxonomy under one `catalog` app.
- Preserve public read APIs and write protection unless the task explicitly changes them.
- Keep PostgreSQL wiring aligned with `product-service`.
- Keep compose startup aligned with PostgreSQL readiness before migrations run, including idempotent bootstrap of `product_db` on reused volumes.
- Do not reintroduce SQLite-only test fallbacks; verify against PostgreSQL wiring.
- When changing models or seed data, update tests and docs in the same change.

## Testing
- Run relevant tests with `python manage.py test catalog`.
- Verify seed counts, filters, and staff-protected create/update/delete when catalog logic changes.

## Dependencies
- Prefer the existing Django/DRF stack before adding new libraries.

## Output expectations
- Explain what changed.
- List touched files.
- Mention tradeoffs or remaining risks.
- Note what you verified.
