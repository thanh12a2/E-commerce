# Phase 4 Neo4j Behavior Graph

## Purpose

Phase 4 imports the synthetic dataset `data_user500.csv` into Neo4j so the graph can be:

- easy to visualize in Neo4j Browser for submission screenshots
- useful for user/category/product context lookup in Phase 5 chat retrieval

## Runtime Wiring

- Neo4j service: `neo4j`
- Browser: `http://localhost:7474/`
- Bolt: `bolt://localhost:7687`
- Chatbot env:
  - `NEO4J_URI`
  - `NEO4J_USERNAME`
  - `NEO4J_PASSWORD`
  - `NEO4J_DATABASE`

Clean import command:

```bash
docker compose exec chatbot_service python manage.py import_behavior_graph --reset
```

## Graph Schema

Nodes:

- `User`
  - `user_ref`
  - `event_count`
  - `session_count`
  - `primary_category_slug`
  - `affinity_total`
- `Behavior`
  - `behavior_id`
  - `behavior_type`
  - `event_ts`
  - `session_id`
  - `step_index`
  - `price_bucket`
  - `device_type`
  - `search_query`
  - `target_next_category_slug`
  - `affinity_weight`
- `Category`
  - `slug`
  - `name`
- `Product`
  - `product_id`
  - `name`
  - `brand`
  - `price`
  - `stock`
  - `category_slug`
  - `category_name`
  - `catalog_source`

Relations:

- `(u:User)-[:PERFORMED]->(b:Behavior)`
- `(b:Behavior)-[:IN_CATEGORY]->(c:Category)`
- `(b:Behavior)-[:ON_PRODUCT]->(p:Product)`
- `(p:Product)-[:BELONGS_TO]->(c:Category)`
- `(u:User)-[:PREFERS {score, share, rank, event_count, last_event_ts}]->(c:Category)`

## Preference Rule

`PREFERS` is derived from aggregate affinity per user/category using weighted behavior signals:

- `search`: `1.0`
- `view_product`: `1.6`
- `chatbot_ask`: `2.4`
- `save_item`: `3.0`
- `compare_item`: `3.2`
- `add_to_cart`: `4.2`
- `checkout`: `5.1`
- `pay_order`: `6.0`

Importer keeps:

- the top category for every user
- plus other categories with `share >= 0.18` and at least 2 events
- capped at `3` preferred categories per user by default

This keeps the graph readable in Browser while still preserving useful user intent signals.

## Files Produced

- Dataset input: `services/chatbot_service/chatbot/artifacts/data_user500.csv`
- Demo image for PDF: `services/chatbot_service/chatbot/artifacts/behavior_graph_demo.svg`
- Query examples: `docs/neo4j_behavior_graph_queries.cypher`

## Suggested Workflow

1. Start services with `docker compose up --build -d`
2. Build chat KB if needed: `docker compose exec chatbot_service python manage.py build_chat_kb --max-products 160`
3. Import graph: `docker compose exec chatbot_service python manage.py import_behavior_graph --reset`
4. Open Neo4j Browser and run queries from `docs/neo4j_behavior_graph_queries.cypher`
5. Use either Browser graph view or the generated SVG for the PDF
