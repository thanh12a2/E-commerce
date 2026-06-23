# AGENTS.md

## Project overview
This service owns payment records for orders. It stores order/user payment identity, amount, status, timestamps, and paid-at state behind internal APIs.

## Goals
- Keep payment state independent from order and shipping ownership.
- Preserve the existing order contract by accepting order IDs as service references instead of foreign keys.

## Coding rules
- Keep `payment_service` API-focused and internal-only by default.
- Protect internal APIs with `PAYMENT_SERVICE_INTERNAL_KEY`; accept `X-Internal-Key` as the primary header.
- Keep database configuration env-driven with `PAYMENT_POSTGRES_*` variables.
- Do not add shipping logic to this service.

## Testing
- Run relevant tests with `python manage.py test payments`.
- Verify create, retrieve, by-order lookup, confirm, cancel, and forbidden internal access when touched.

## Dependencies
- Prefer Django, DRF, and `psycopg2-binary` before adding new libraries.

## Output expectations
- Explain what changed.
- List touched files.
- Mention tradeoffs or remaining risks.
- Note what you verified.
