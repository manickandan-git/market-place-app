# Agentic AI assistant (`assistant-service`)

## Context

The marketplace has 9 backend services behind an API gateway and a complete
buyer storefront (`apps/web`, Next.js). The user wants to add an agentic AI
layer for product search, pricing, inventory, and policy questions. Locked-in
decisions from the clarifying round:

- **Audience**: both buyers and sellers/ops, but scope v1 to buyers; the
  seller/ops copilot is phase 2, built on the same core.
- **Agent actions**: read tools everywhere, plus one buyer-side write action
  — adding items to the buyer's own cart. Checkout/payment stay entirely
  outside the agent's reach.

## Grounding facts (from reading the actual code, not assumed)

These directly shape the design below:

- **Search today is `Product.name.ilike(f"%{query}%")`** — name only, not
  description/brand, no full-text/semantic matching
  (`services/product-service/app/repositories/catalog_repository.py:92-93`).
  A `services/search-service/` directory already exists but is an empty
  scaffold — the team anticipated this need but never built it.
- **Pricing is static per-variant** (`price_amount`, `compare_at_price` on
  `ProductVariant`) — no tiers, no history, no dynamic pricing anywhere.
  Cart and order snapshot price at time of use (`ProductClient.get_snapshot`
  in `services/cart-service/app/clients.py`) rather than re-reading live.
- **Policy content doesn't exist anywhere in the repo.** The only "policy"
  hit is `user-service`'s `ConsentType` enum, which logs that a user
  *accepted* a policy version — it stores no actual policy text. This is
  greenfield.
- **`GET /api/v1/availability/{sku}` is public**, already gateway-allowlisted,
  no auth needed (`services/inventory-service/app/routes/inventory.py:48-64`).
  Seller-scoped stock views (`/seller/inventory?low_stock_only=true`) require
  a seller/admin JWT — this is what phase 2 will use.
- **Cart's `POST /api/v1/cart/items` takes a buyer's own `Authorization:
  Bearer` JWT directly** (`OptionalPrincipal`, no scope check) — a signed-in
  buyer's cart auto-creates on first use with `version: 1`
  (`services/cart-service/app/services/cart_service.py:105-146`). No new
  service-token or scope is needed for the add-to-cart tool — it's a pure
  token-relay of the buyer's own credential, same as every gateway call the
  storefront already makes.
- **Gateway extension is a two-line pattern**: a `Route(prefix,
  upstream_setting)` tuple in `services/api-gateway/app/services/routing.py`'s
  `ALLOWLIST`, plus a `assistant_service_url` setting in
  `services/api-gateway/app/config.py` — same pattern every existing service
  uses.

## Architecture

```
Browser (apps/web)
  │  chat widget → Route Handler (server-side, same BFF pattern as the rest
  │  of the storefront: attaches Authorization: Bearer <mp_access_token>
  │  from the httpOnly cookie if signed in, omits it for guests)
  ▼
POST /api/v1/assistant/chat  (streamed response)
  ▼
API Gateway :9000  ── new Route("/api/v1/assistant", "assistant_service_url")
  ▼
assistant-service :8012  (NEW — packaged layout per CLAUDE.md's convention
                           for brand-new services)
  ├─ app/agent/            Claude tool-use loop (Anthropic Messages API,
  │                        latest Claude model) — the model decides which
  │                        tool(s) to call per turn, streams the reply back
  ├─ app/tools/            one file per tool: schema + handler, each handler
  │                        is a thin call into app/clients.py
  ├─ app/clients.py        typed HTTP clients to product/inventory/cart/
  │                        order-service — same convention as every other
  │                        service's app/clients.py
  ├─ app/models/           PolicyDocument (topic, version, raw body),
  │                        PolicyChunk (document_id FK, chunk_text,
  │                        chunk_index, embedding vector(384)),
  │                        ToolInvocationAudit (who, tool, args, result,
  │                        request_id) — the audit model mirrors the pattern
  │                        order-service and inventory-service already use
  ├─ app/rag/               chunking + local embedding (sentence-transformers,
  │                        e.g. all-MiniLM-L6-v2, loaded in-process) +
  │                        pgvector cosine-similarity retrieval — the only
  │                        in-process ML model in the repo; every other
  │                        service is pure FastAPI with no local model
  ├─ Postgres (dedicated,  policy chunks + embeddings (pgvector extension)
  │   pgvector ext.)        + audit log — same "each service owns its own
  │                        DB" convention as every other service
  └─ Redis                 ephemeral conversation/session state, short TTL —
                           this service is an orchestrator, not a new
                           system of record for product/cart/order truth
```

Nothing here bypasses existing ownership: product-service still owns
products, inventory-service still owns stock, cart-service still owns the
cart. assistant-service only ever *reads* from them via HTTP (through the
gateway or direct internal URL, matching how order-service already calls
inventory/product/cart today) and, for the one write action, forwards the
buyer's own JWT so cart-service enforces the exact same rules it already
enforces for the storefront UI.

## Tool catalog (v1, buyer-facing)

| Tool | Downstream call | Auth |
|---|---|---|
| `search_products(query, category?)` | `GET product-service /api/v1/products?q=` | none (public) |
| `get_product(slug)` | `GET product-service /api/v1/products/by-slug/{slug}` | none (public) |
| `list_categories()` | `GET product-service /api/v1/categories` | none (public) |
| `get_availability(sku)` | `GET inventory-service /api/v1/availability/{sku}` | none (public) |
| `get_policy(query)` | local pgvector similarity search over `PolicyChunk` (top-k, then LLM synthesizes an answer from the retrieved chunks) | none (public) |
| `get_my_orders()` / `get_order_status(order_id)` | `GET order-service /api/v1/orders[/​{id}]` | relays buyer's Bearer JWT — unavailable to guests, agent should just say "sign in to check your orders" |
| `add_to_cart(product_id, variant_id, qty)` | `GET cart-service /api/v1/cart` (read version) then `POST /api/v1/cart/items` | relays buyer's Bearer JWT **or** the guest `X-Cart-Token` cookie the storefront already sets — same dual-mode cart-service already supports |

Every tool call gets logged to `ToolInvocationAudit` (actor, tool, args,
result, `X-Request-ID`) — this matters specifically because `add_to_cart` is
a real side effect, and it's the same discipline order-service/inventory-service
already apply to their own mutations.

## Search quality: don't build semantic search for v1

The name-only ILIKE match is weak for natural-language queries ("wireless
earbuds under $50" won't match "Bluetooth Headphones"). Two options:

- **v1 (recommended)**: let the LLM compensate — it extracts likely
  keyword(s)/category from the user's phrasing and tries `search_products`
  a couple of times, falling back to `list_categories` + browse. Zero new
  infrastructure, ships with everything else.
- **Later**: real semantic search (embeddings + pgvector) belongs in the
  already-scaffolded but empty `services/search-service/`, not inside
  assistant-service — keeps "search relevance" and "agent orchestration" as
  separate concerns, consistent with how every other responsibility in this
  repo is split. Flag as a follow-up, not part of this build.

## Policy content v1 (RAG)

Nothing else in the repo owns this domain, so assistant-service becomes the
owner. Scope stays **policy-only** for v1 (return/shipping/refund text) —
not a general help-center/FAQ knowledge base; that's a real scope expansion
to consider later, not part of this build.

- **Storage**: `pgvector` extension enabled on assistant-service's own
  Postgres (no new infra — consistent with "each service owns its own DB").
  `PolicyDocument` (topic, version, raw body) holds the source text;
  `PolicyChunk` (document_id FK, chunk_text, chunk_index,
  `embedding vector(384)`) holds paragraph-level chunks + embeddings.
- **Embedding model**: local, in-process `sentence-transformers`
  (e.g. `all-MiniLM-L6-v2`, 384-dim) — no external embedding API/vendor
  dependency. This is the one service in the repo that loads an ML model
  in-process; note it in the service README since it changes container
  size/cold-start relative to every other (pure FastAPI, no local model)
  service, and add `sentence-transformers` to its `pyproject.toml`.
- **Ingestion**: no admin UI in v1 — a seed script/migration chunks and
  embeds real return/shipping/refund text at deploy time. A future admin
  endpoint can re-ingest edited policy text without a redeploy since the
  seam (`PolicyDocument` + re-chunk/re-embed) is already there.
- **Retrieval**: `get_policy(query)` embeds the incoming question with the
  same local model, does a pgvector cosine-similarity top-k (e.g. k=3–5)
  against `PolicyChunk`, and returns the matched chunks (with source
  topic/version) as the tool result — the agent synthesizes the answer from
  retrieved chunks rather than returning one exact-topic block verbatim, so
  it can answer phrasing that doesn't match a topic name exactly.

## Auth at the gateway

`/api/v1/assistant/chat` is allowlisted like the public catalog routes — it
must accept anonymous callers (guests can search/ask policy questions).
assistant-service reads `Authorization` if present (optional, not required)
to decide which tools it exposes that turn, the same `OptionalPrincipal`
pattern cart-service already uses. **Verify against
`services/api-gateway/docs/route-allowlist.md` and the edge token_verifier's
route-scoping when implementing** — confirm the edge JWT check added earlier
this session is scoped per-route and won't block anonymous chat.

## Frontend integration

- New chat widget in `apps/web` (floating panel or `/assistant` page).
- A Route Handler (`app/api/assistant/chat/route.ts`) is the only place that
  attaches the bearer token server-side and streams the response back —
  same "tokens never reach client JS" rule as the rest of the storefront.
- `add_to_cart` results should trigger the same cart-badge refresh the
  existing `SiteHeader`/cart Server Actions already do.

## Phase 2 (seller/ops, read-only)

Same service, same agent loop, new tools scoped to a seller's own JWT
(token-relay, same pattern): `get_low_stock_items()` →
`GET inventory-service /seller/inventory?low_stock_only=true`, plus
comparable-listing/price-visibility tools. Deliberately **no** write-suggestion
tool yet — that wasn't the scope selected for this build; if wanted later,
the pattern would be "agent drafts a suggestion, seller clicks Apply, a
normal authenticated PATCH fires" (agent never calls a write endpoint
itself), mirroring how `add_to_cart` today only ever acts through the
buyer's own already-authorized identity.

## Framework choices: revisit if...

v1 deliberately stays hand-rolled: a plain Anthropic Messages API tool-use
loop (`app/agent/`) and raw pgvector SQL for retrieval, no LangGraph,
LangChain, or MCP. None of the three earn their weight for a single
7-tool buyer loop with one hand-seeded pgvector table — but each has a
concrete condition under which it would:

- **LangGraph** — revisit if Phase 2 actually builds the "agent drafts a
  suggestion, seller clicks Apply" write-suggestion pattern (currently
  explicitly out of scope there). That's an interrupt/resume workflow —
  propose, pause for human approval, resume — which is the checkpointing
  primitive LangGraph is built for. Also revisit if a supervisor ever needs
  to route between distinct specialized agents (e.g. buyer agent + separate
  seller-ops agent) instead of one flat loop with a role-scoped tool subset.
- **LangChain** — revisit if policy ingestion moves from hand-authored
  seed text to arbitrary uploaded documents (PDF/Word/scans), where its
  document-loader ecosystem earns its keep. Also revisit if RAG scope grows
  from policy-only into a general knowledge base (FAQs, help articles,
  seller guides) — the general-knowledge-base option considered and turned
  down earlier in this plan — where pluggable loaders/retrievers beat one
  hardcoded pgvector query.
- **MCP** — revisit the moment a second client needs these tools outside
  the buyer chat widget — e.g. internal support staff querying
  policy/product/inventory via Claude Desktop, or a Phase 2 seller-ops
  integration meant to be used through Claude Desktop/Code rather than only
  the storefront widget. Not needed while assistant-service's own loop is
  the only caller.

## Build-out phases

1. Scaffold `assistant-service` (packaged layout, Postgres, Redis, health
   routes), gateway `Route` + settings, auth-service needs **no** new
   client-credentials registration for v1 (pure token-relay, no service
   identity required).
2. Tool clients + handlers for the 4 public read tools (search, product,
   categories, availability). Enable `pgvector`, build the chunk/embed
   ingestion script, seed real policy text, wire up `get_policy` retrieval.
   Verify via the agent loop answering real questions against the live
   catalog and against policy phrasing that doesn't match a topic name
   verbatim (the actual point of doing this as RAG instead of exact lookup).
3. Buyer-context tools: `get_my_orders`/`get_order_status`,
   then `add_to_cart` (guest + authenticated paths). Verify a full "find a
   product → check stock → add to cart" conversation end-to-end.
4. Streaming chat endpoint + `apps/web` widget wired through the Route
   Handler.
5. Phase 2: seller-scoped read tools, reusing the same core.

## Verification

- Each tool is independently testable via direct HTTP call to
  assistant-service before wiring into the agent loop (unit-test the
  client + handler, same as other services' `tests/`).
- End-to-end: drive the chat widget with `browser-automation` against the
  real running stack — "find me a widget under $30", "is it in stock",
  "add it to my cart", confirm the cart badge updates and `GET /api/v1/cart`
  shows the real item — same rigor as this session's earlier UI-to-backend
  sweep.
- Audit log: confirm a `ToolInvocationAudit` row is written for the
  `add_to_cart` call with the correct actor and request ID.
