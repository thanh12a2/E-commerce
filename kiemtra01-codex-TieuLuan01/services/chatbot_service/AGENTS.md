# AGENTS.md

## Project overview
This service is the Django chatbot backend. It exposes `/api/chat/reply/` and `/api/chat/ingest-behavior/`, reads the unified `product_service` catalog, manages file-based chatbot artifacts, stores `BehaviorEvent` data in PostgreSQL, imports a Neo4j behavior graph for Phase 4/5 context retrieval, and calls the configured LLM provider with fallback behavior when external calls fail.

## Goals
- Keep changes small and easy to review.
- Prefer fixing root causes over patching symptoms.
- Do not break chat reply, retrieval, recommendation, behavior tracking, or fallback flows.

## Coding rules
- Follow the existing `chatbot` app structure and keep request handling, retrieval, behavior logic, and provider integration in their current modules.
- Preserve current API response fields and runtime provider behavior unless the task requires a change.
- Keep provider env vars, `PRODUCT_SERVICE_URL`, and artifact paths aligned with Docker/runtime setup.
- Keep Neo4j graph wiring env-driven and optional; graph import commands must not break `/api/chat/reply/` or existing PostgreSQL-backed behavior persistence when Neo4j is unavailable.
- Keep PostgreSQL bootstrap idempotent.
- Keep `POSTGRES_DB` wiring env-driven so the compose/runtime contract stays explicit for `chatbot_db`.
- Keep chatbot artifacts file-based under `/app/chatbot/artifacts`.
- Treat `user_service`'s `backfill_chatbot_behavior` command as the standard recovery path for `BehaviorEvent`.

## Testing
- Run relevant tests with `python manage.py test chatbot`.
- Verify `build_chat_kb`, `train_behavior_model`, `/api/chat/reply/`, and the proxied `/customer/chatbot/reply/` flow when chatbot logic changes.

## Dependencies
- Prefer the existing Django, DRF, `requests`, and artifact-based approach before adding new libraries; if Neo4j is required, keep it service-local to `chatbot_service`.
- Do not reintroduce SQLite fallback unless explicitly requested.

## Output expectations
- Explain what changed.
- List touched files.
- Mention tradeoffs or remaining risks.
- Note what you verified.
