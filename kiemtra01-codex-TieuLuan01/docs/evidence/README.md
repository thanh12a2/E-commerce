# Evidence Screenshots

Store the final UI screenshots for the submission PDF here:

- `screenshots/dashboard-ai.png`
- `screenshots/cart-ai.png`
- `screenshots/chat-widget.png`
- `screenshots/neo4j-browser.png`
- `screenshots/neo4j-browser-2.png`
- `screenshots/gateway-8080.png`

Preferred capture paths:

- Use `http://localhost:8080/` for customer, staff, gateway, auth API, catalog API, and chatbot API evidence because Nginx is the primary entrypoint.
- Use `http://localhost:7474/` for Neo4j Browser evidence.
- Keep AI artifacts under `services/chatbot_service/chatbot/artifacts/`; do not copy model or KB files into this screenshot folder.

Keep filenames stable so `docs/phase-6-submission-kit.md` and `README.md` continue to point at the same evidence paths.
