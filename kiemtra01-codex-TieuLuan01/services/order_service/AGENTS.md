# AGENTS.md

## Project overview
This service owns commerce state outside the UI. It stores cart, saved items, compare items, orders, order items, payment/shipping snapshots, customer analytics, behavior-source export, and legacy order import. Payment records live in `payment_service`; shipment records live in `shipping_service`.

## Goals
- Keep cart/checkout/order logic stable behind internal APIs.
- Keep checkout/payment/shipping orchestration stable while delegating payment records to `payment_service` and shipment records to `shipping_service`.
- Preserve snapshot-based order history so old catalog data is not required at read time.

## Coding rules
- Keep `order_service` API-focused and internal-only by default.
- Reuse helpers inside the `orders` app before adding new layers.
- Preserve payment status and shipping status as separate order snapshots; do not collapse them back into order-owned record lifecycles.
- Keep MySQL bootstrap aligned with Docker healthchecks.
- Keep MySQL bootstrap able to reconcile reused Docker volumes for `order_db` without manual volume deletion.
- Keep internal APIs protected with `ORDER_SERVICE_INTERNAL_KEY`; do not rely on host-published access. External smoke checks should go through Nginx gateway port `8080`.
- Keep service-client calls aligned with `PAYMENT_SERVICE_URL`, `SHIPPING_SERVICE_URL`, `PAYMENT_SERVICE_INTERNAL_KEY`, and `SHIPPING_SERVICE_INTERNAL_KEY`.
- Keep legacy import logic compatible with `user_service`'s `LegacyUserMapping`.

## Testing
- Run relevant tests with `python manage.py test orders`.
- Verify cart/saved/compare, checkout with shipping data, pay order, staff shipping update, analytics, and legacy import helpers when touched.

## Dependencies
- Prefer Django, DRF, `requests`, and PyMySQL before adding new libraries.

## Output expectations
- Explain what changed.
- List touched files.
- Mention tradeoffs or remaining risks.
- Note what you verified.
