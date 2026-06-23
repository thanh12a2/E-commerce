# AGENTS.md

## Project overview
This service owns shipment records for orders. It stores order/user shipment identity, recipient address snapshots, shipment status, and timestamps behind internal APIs.

## Goals
- Keep shipping state independent from order and payment ownership.
- Preserve order references as plain IDs instead of cross-service foreign keys.
- Keep shipment lifecycle transitions aligned with the order service shipping transition graph.

## Coding rules
- Keep `shipping_service` API-focused and internal-only by default.
- Protect internal APIs with `SHIPPING_SERVICE_INTERNAL_KEY`; accept `X-Internal-Key` as the primary header.
- Keep database configuration env-driven with `SHIPPING_POSTGRES_*` variables.
- Do not add payment logic to this service.

## Testing
- Run relevant tests with `python manage.py test shipments`.
- Verify create, retrieve, by-order lookup, status transition, and forbidden internal access when touched.

## Dependencies
- Prefer Django, DRF, and `psycopg2-binary` before adding new libraries.

## Output expectations
- Explain what changed.
- List touched files.
- Mention tradeoffs or remaining risks.
- Note what you verified.
