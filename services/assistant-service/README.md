# Marketplace Assistant Service

Agentic AI assistant for the marketplace storefront. A buyer-facing chat
loop (Claude tool-use over the Anthropic Messages API) that can search the
catalog, check availability, answer policy questions, look up a buyer's own
orders, and add or remove items in a buyer's own cart. It owns no product,
inventory, cart, or order data — every tool call either reads from the
owning service over HTTP or, for its two write actions (`add_to_cart`,
`remove_from_cart`), relays the buyer's own JWT into cart-service so
cart-service enforces its existing rules unchanged.

## Status

**Phases 1-4 are complete.** Nine tools are implemented and tested
(`search_products`, `get_product`, `list_categories`, `get_availability`,
`get_policy`, `get_my_orders`, `get_order_status`, `add_to_cart`,
`remove_from_cart`), backed by a working pgvector RAG pipeline (local
`sentence-transformers` embeddings, chunked and seeded return/shipping/refund
policy content, cosine-similarity retrieval). The Anthropic Messages API
tool-use loop (`app/agent/loop.py`) is wired up behind a live
`POST /api/v1/assistant/chat` endpoint (`app/routes/chat.py`), and `apps/web`'s
`ChatWidget.tsx` talks to it through `chat.ts` — this is a plain
request/response endpoint, not a streaming one, despite the original
roadmap item 4 below calling for streaming. See Roadmap below for what's
next.

## Local ports

| Service | Port |
|---|---:|
| Auth | 8001 |
| Notification | 8002 |
| User | 8003 |
| Product | 8004 |
| Inventory | 8005 |
| Cart | 8006 |
| Order | 8007 |
| Payment | 8008 |
| Shipping | 8009 |
| Assistant | 8012 |
| Assistant PostgreSQL | 5442 |

Adjust the ports in `.env` if your local layout differs.

## Start locally with PowerShell

```powershell
Copy-Item .env.example .env
uv sync
docker compose up -d marketplace-assistant-db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8012
```

Open:

```text
http://localhost:8012/docs
http://localhost:8012/health
http://localhost:8012/ready
```

Run tests and lint:

```powershell
uv run pytest -v
uv run ruff check .
```

Or via the full Docker stack from the repo root:

```powershell
docker compose up --build marketplace-assistant-db marketplace-assistant-service
```

## Required configuration

```env
DATABASE_URL=postgresql+asyncpg://marketplace:marketplace@localhost:5442/assistant_service
JWT_JWKS_URL=http://localhost:8001/.well-known/jwks.json
JWT_ISSUER=http://localhost:8001
JWT_AUDIENCE=marketplace-api
```

`JWT_ISSUER`/`JWT_AUDIENCE`/`JWT_JWKS_URL` must match auth-service's own
values byte-for-byte, same convention as every other service in this repo —
a mismatch here is the most common source of `401 Invalid or expired access
token` errors.

Downstream service URLs default to `PRODUCT_SERVICE_URL=http://localhost:8004`
and `INVENTORY_SERVICE_URL=http://localhost:8005` (see `app/config.py`) —
override them if your local layout differs. `EMBEDDING_MODEL_NAME` defaults
to `all-MiniLM-L6-v2` (384-dim); changing it to a model with a different
output dimension will fail fast with a clear error rather than a confusing
insert failure, since `PolicyChunk.embedding` is fixed at `vector(384)` in
the schema. No client-credentials registration in auth-service is needed for
this service: every tool is designed as either an unauthenticated public
read or a pure relay of the buyer's own JWT, never a service-to-service
scoped token.

Seed the policy content used by `get_policy` (return/shipping/refund text)
after migrations are applied:

```powershell
uv run python -m app.rag.seed
```

This wipes and re-inserts all `PolicyDocument`/`PolicyChunk` rows from
`app/rag/policy_content.py` — safe to re-run after editing that file.

## Gateway access

Proxied at `POST /api/v1/assistant/*` via `services/api-gateway`
(`http://localhost:9000`), allowlisted as PUBLIC — it must accept anonymous
callers, since guests can search the catalog and ask policy questions
without signing in. See `services/api-gateway/docs/route-allowlist.md`.

## Roadmap

1. ~~Service scaffold: packaged layout, dedicated pgvector-capable Postgres,
   Alembic, Docker Compose, gateway wiring.~~ **(done)**
2. ~~Read-only tool clients — `search_products`, `get_product`,
   `list_categories`, `get_availability` — plus a pgvector-backed RAG
   pipeline (local `sentence-transformers` embeddings, chunked policy
   content) for `get_policy`.~~ **(done)**
3. ~~Buyer-context tools — `get_my_orders`, `get_order_status`, then
   `add_to_cart` (guest and authenticated paths), all via JWT/cart-token
   relay, no new service credentials.~~ **(done — `remove_from_cart` was
   added alongside `add_to_cart` as a second write tool)**
4. ~~Chat endpoint (`POST /api/v1/assistant/chat`) and the `apps/web` chat
   widget.~~ **(done, as a plain request/response endpoint — not the
   streaming one originally scoped here; revisit streaming if response
   latency becomes a problem)**
5. Phase 2 of the wider plan: seller/ops read-only tools on the same core
   (e.g. `get_low_stock_items`).

## Design notes

- **Pure orchestrator, not a new system of record.** Product, inventory,
  cart, and order data stay owned by their existing services.
- **`add_to_cart` and `remove_from_cart` are the only writes the agent can
  ever perform**, and both work by relaying the buyer's own JWT (or guest
  `X-Cart-Token`) into cart-service — no elevated or service-scoped access.
  `loop.py` caps writes at one per turn regardless of which write tool(s)
  Claude requests.
- **No LangGraph, LangChain, or MCP for v1.** A hand-rolled Anthropic
  Messages API tool-use loop is enough for a single ~7-tool buyer flow, and
  raw pgvector SQL is enough for retrieval. Revisit LangGraph if a
  human-in-the-loop write-suggestion flow gets built for the seller/ops
  phase; revisit MCP if a second client (e.g. an internal tool via Claude
  Desktop) needs these tools outside the chat widget.

## Guardrails

The chat endpoint has a scope-restricting system prompt, a per-caller rate
limit (keyed off `X-Forwarded-For` when behind the gateway), request size
bounds, a PII trim on order data, a wall-clock timeout, a write-tool-per-turn
cap, and a content-derived idempotency key on `add_to_cart` to make a
same-item retry after a timeout a safe no-op. See `docs/guardrails.md` for
the full list — nothing on that list is currently open.

## Observability

Implemented: structured JSON log lines (`app/event_logger.py`) for every
completed `/chat` request (`request_id`, tool calls, `stop_reason`, latency,
Anthropic input/output token counts) and every downstream HTTP call, plus a
Loki/Promtail/Grafana stack (`docker-compose.yml`, dev-only) with a
dashboard (`infrastructure/monitoirng/dashboards/assistant-service-observability.json`)
covering request rate, latency, token usage, stop reasons, downstream call
latency/status by service, and rate-limit 429s. See `docs/observability.md`
for what's covered and what's still a gap.
