# AGENTS.md

## Project overview
This service is the shared auth/UI edge behind the Nginx gateway. It owns customer and staff web flows, Django admin, browser session auth, JWT API auth, editorial content, chatbot proxy, gateway inspection views, and legacy user migration. It reads catalog data from `product_service`, commerce state from `order_service`, and chat replies from `chatbot_service`.

## Goals
- Keep customer/staff routes stable.
- Prefer orchestration over duplicating business logic from downstream services.
- Do not store cart/order/saved/compare state locally.

## Coding rules
- Keep `/customer/*`, `/staff/*`, `/admin/`, and `/customer/chatbot/reply/` routes stable unless the task explicitly changes them.
- Keep Nginx `http://localhost:8080/` as the primary public entrypoint; direct `8000`/`8003` ports remain debug/dev surfaces.
- Keep Django session UI auth and JWT API auth coexisting. Do not change `/api/auth/register/`, `/api/auth/token/`, `/api/auth/token/refresh/`, or `/api/auth/me/` without updating gateway docs and smoke commands.
- Reuse helpers in `customer/services.py`, `customer/api_gateway/`, management commands, and the `staff` app before adding new layers.
- Keep `user_service` as the only auth source for admin/staff/customer accounts.
- Keep blog/testimonial/editorial content local to this service.
- Keep MySQL bootstrap aligned with Docker healthchecks.
- Keep MySQL bootstrap able to reconcile reused Docker volumes for `user_db` without manual volume deletion.
- Keep downstream URLs aligned with `PRODUCT_SERVICE_URL`, `ORDER_SERVICE_URL`, and `CHATBOT_SERVICE_URL`, and send `ORDER_SERVICE_INTERNAL_KEY` on every order-service call.

## Testing
- Run relevant tests with `python manage.py test customer staff`.
- Verify customer login/register/dashboard/cart/checkout/orders/chatbot and staff login/dashboard/items/customers/orders when related flows change.
- Verify `migrate_legacy_users` and `backfill_chatbot_behavior` when migration/recovery logic changes.

## Dependencies
- Prefer Django, DRF, `requests`, and the existing template/UI stack before adding new libraries.

## Output expectations
- Explain what changed.
- List touched files.
- Mention tradeoffs or remaining risks.
- Note what you verified.
