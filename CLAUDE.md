# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A microservices-based marketplace platform. Each service is an independently
deployable FastAPI + PostgreSQL application living under `services/<name>-service/`,
managed with `uv`. The root `docker-compose.yml` wires all services, their
databases, and Redis together for local development. `tests/integration-tests`
is a separate `uv` project that exercises the running services over real HTTP.

| Service | Port | Responsibility |
|---|---|---|
| auth-service | 8001 | Registration, login, email verification, password recovery, JWT/session issuance, JWKS |
| notification-service | 8002 | Transactional email delivery, Celery-backed retries |
| user-service | 8003 | Buyer/seller profiles, addresses, preferences, consent, privacy/deactivation |
| product-service | 8004 | Seller-owned product catalog, categories, variants/SKUs, public catalog reads |
| inventory-service | 8005 | Warehouses, seller stock, availability, reservations, movements, low-stock events |
| cart-service | 8006 | Shopping intent and current price snapshots |
| order-service | 8007 | Checkout order snapshots and order lifecycle |
| payment-service | 8008 | Stripe payment authorization, capture, and refunds |
| shipping-service | 8009 | Shipment records, carrier/tracking info, drives Order's fulfillment callback |
| api-gateway | 9000 | Reverse proxy fronting every public route: allowlisting, CORS, correlation IDs, per-request timeouts, per-upstream circuit breaker, fail-fast JWT signature/expiry check (not authorization). No database, no business logic — breaks the FastAPI+PostgreSQL pattern above by design. |
| assistant-service | 8012 | Buyer-facing agentic AI chat (Claude tool-use over the Anthropic Messages API): catalog search, availability, policy Q&A (pgvector RAG), a buyer's own orders, and add/remove-cart writes relayed through the buyer's own JWT. Owns no product/inventory/cart/order data itself. |

`services/audit-service/` and `services/search-service/` exist as empty
directories only (no code, not even a scaffold) — do not treat them as
implemented services or add ports/endpoints for them until something is
actually built there.

`auth-service` (the Identity Service) is the sole authority for credentials,
roles, sessions, and JWT issuance. Every other service validates
Identity-issued JWTs via JWKS (RS256, `kid`-based key lookup) and treats the
token's immutable `sub` claim as `user_id` — no other service stores
passwords or issues tokens. Service-to-service internal endpoints are
protected either by a scoped JWT (e.g. `inventory:sync`, `orders:payment`) or
by a static `X-Internal-API-Key` header (Notification Service).

Each service owns a dedicated Postgres database (and Redis where needed);
there is **no cross-service database access**. Cross-service reads happen
over internal HTTP APIs (e.g. Inventory pulls product/variant projections
from Product via `PUT /api/v1/internal/catalog-skus/{variant_id}`; Order
resolves seller ownership from Product and reserves stock from Inventory
during checkout). Service containers reach each other by container name on
the Docker network (e.g. `marketplace-auth-service`); host-side tooling uses
the published `localhost` ports above.

### JWT/env var conventions

`JWT_ISSUER`, `JWT_AUDIENCE`, and `JWT_JWKS_URL` must be set to identical
values (byte-for-byte) across every service that verifies tokens — auth-service
defines the issuer/audience it stamps into tokens (`JWT_ISSUER`, `JWT_AUDIENCE`
in its `.env`), and every consuming service (order, cart, inventory, product,
user, payment, ...) must echo those same values plus point `JWT_JWKS_URL` at
auth-service's `/.well-known/jwks.json`. These three names are consistent
across all services, including user-service — even though user-service
prefixes every other setting with `USER_SERVICE_` (see `app/config.py`), its
identity fields are aliased to the bare `JWT_*` names specifically so this
convention holds everywhere. A mismatch (e.g. `localhost` vs a container name
in `iss`) is the single most common source of `401` errors when wiring up a
new service or running integration tests — check this before debugging
further.
Internal-only endpoints use one of two separate mechanisms, don't confuse
them: scoped service JWTs (validated the same way as user JWTs, but checked
for a `scope` claim, e.g. `inventory:sync`, `orders:payment`) for
Order/Inventory/Product/Payment, vs. a static `INTERNAL_API_KEY` shared secret
sent as `X-Internal-API-Key` for Notification only. Scoped service JWTs are
obtained via client-credentials at `POST /api/v1/auth/service-token`
(auth-service), whose registered clients live in a hardcoded `registry` dict
in `services/auth-service/app/routes.py` (`issue_service_token`) — adding a
new service-to-service caller means adding both a `Settings` field pair
(`<name>_client_id`/`<name>_client_secret`) and a registry entry there, not
just configuring the calling service.

## Working across services

Every service is a standalone `uv` project — there is no shared virtualenv or
monorepo-wide dependency file. Commands below must be run from inside the
specific `services/<name>-service/` directory (or `tests/integration-tests`).

### Common per-service commands

```powershell
uv sync                                    # install deps (creates .venv)
uv run alembic upgrade head                # apply migrations
uv run uvicorn app.main:app --reload --port <service-port>
uv run pytest                              # run this service's unit tests
uv run pytest tests/test_some_file.py::test_name   # run a single test
uv run ruff check .                        # lint
uv run ruff format .                       # format
```

Every service also exposes these via `make install|run|test|lint|format|migrate|docker-up|docker-down`
(and `make check` = lint + test) — targets and port numbers are consistent
across all ten database-backed services (everything in the table above
except `api-gateway`, which has no database and so no `migrate` target).

### Full stack (Docker)

```powershell
docker compose up --build                  # start every service + db + redis
docker compose up --build marketplace-auth-db marketplace-auth-service ...  # start a subset
docker compose down                        # stop
docker compose down -v                     # stop and wipe db volumes (destructive)
docker compose exec <service>-service alembic upgrade head
```

Each API container applies its own Alembic migrations on startup. Swagger
docs are served at `http://localhost:<port>/docs` for every service.
`mailpit` (dev email capture, `--profile dev`) is at `http://localhost:8025`.

### Integration tests (`tests/integration-tests`)

A separate `uv` project (`integration_tests/`) that makes real HTTP calls
against running services — it never imports service code or touches another
service's database. Requires services to be up with migrations applied, and
short-lived JWTs for buyer/seller/admin/inventory-sync identities placed in
`.env.integration` (copy from `.env.integration.example`).

```powershell
cd tests/integration-tests
uv sync
uv run pytest integration_tests/test_30_product_inventory.py -m integration -v -s   # single suite
./run-integration.ps1                      # full suite
# equivalent: uv run pytest -m integration -v
```

All services validating a JWT must agree on issuer/audience exactly — a
`localhost` vs container-name mismatch in `iss` is the most common failure
mode (`401 Invalid or expired access token`). See
`tests/integration-tests/README.md` for the full troubleshooting table
(role/scope 403s, notification adapter setup, Docker networking).

## Per-service architecture (FastAPI convention)

Services share a consistent internal layout, most explicitly in
order-service and cart-service:

- `app/main.py` — FastAPI app construction: CORS, correlation-ID middleware,
  router registration, exception handler registration.
- `app/config.py` — `pydantic-settings`-based `Settings`, loaded via
  `get_settings()`.
- `app/auth.py` / `app/dependencies/auth.py` — JWT verification via
  `PyJWKClient` against the Identity Service's JWKS URL; produces a
  `Principal` (subject UUID, roles, scopes, raw claims) via FastAPI
  `Depends`. `require_roles(...)` / `require_scope(...)` dependency
  factories gate routes.
- `app/models.py` / `app/models/` — SQLAlchemy async ORM models.
- `app/repository.py` / `app/repositories/` — data access layer.
- `app/service.py` / `app/services/` — business logic/orchestration,
  separate from route handlers.
- `app/routes.py` / `app/routes/` — FastAPI routers (`health_router` is
  always separate and unauthenticated).
- `app/schemas.py` / `app/schemas/` — Pydantic request/response models.
- `app/exceptions.py` — domain exceptions + `register_exception_handlers(app)`.
- `app/clients.py` — HTTP clients for calling other services internally.
- `app/middleware.py` / `app/middleware/` — e.g. correlation-ID propagation.
- `alembic/` — migrations, applied on container startup (not automatically
  in local `uv run` workflows — run `alembic upgrade head` explicitly).

Some services (cart, inventory, payment) split these into packages
(`app/routes/`, `app/schemas/`, `app/models/`, `app/services/`,
`app/dependencies/`, `app/middleware/`); others (auth, user, product, order)
keep them as flat modules (`app/auth.py`, `app/routes.py`, etc.) — the split
isn't strictly chronological (order is one of the newest services but stayed
flat). Follow whichever pattern the service you're editing already uses;
don't retrofit an existing flat service to packaged just for consistency —
it's pure churn risk on working code for a cosmetic win. **For any brand-new
service, use the packaged layout** — it scales better once a service has
more than one concern (this is a project-structure choice, not a SOLID
question; both layouts can separate responsibilities equally well within
routes/service/repository/schema layers).

Each service's own `README.md` documents its public/internal API surface and
service-specific boundaries (owns X, does not own Y) — read it before adding
endpoints or making cross-service calls, since the boundaries are enforced
by convention, not by code.

order-service additionally documents its Inventory checkout contract
(batch reservation endpoints Inventory needs to expose before live
end-to-end checkout works) in `services/order-service/docs/inventory-checkout-contract.md`.

## Known gaps / in-progress work

- **Inventory batch reservation endpoints are now implemented**
  (`POST /api/v1/internal/checkout/reservations/batch`,
  `/{group_id}/commit`, `/{group_id}/release` in `services/inventory-service`)
  per `services/order-service/docs/inventory-checkout-contract.md`. Lines are
  resolved by `(seller_id, sku)` — never a client-supplied
  `inventory_item_id` — and a line's quantity can split across more than one
  warehouse row for that SKU, sharing one `reservation_group_id`. Commit and
  release are idempotent at the group level (repeat calls on an
  already-committed/released group are safe no-ops); a mixed-status group
  (partially committed/released) is rejected as a conflict rather than
  partially applied.
  Fixed alongside this: `InventoryService._snapshot()` (used for audit-log
  before/after rows) previously either crashed with `MissingGreenlet` when
  reading a column expired by a prior flush, or — worse — called
  `session.refresh()` on objects with *unflushed* pending changes, silently
  reverting them (e.g. a reservation's `status = COMMITTED` write could be
  discarded before it was ever persisted). This affected every mutating
  method in the service (`create_reservation`, `commit_reservation`,
  `adjust_stock`, etc.), not just the new batch endpoints — it's now fixed
  service-wide by flushing (never refreshing) dirty/new objects before
  snapshotting them.
- **Payment service now exists** (`services/payment-service`, port 8008,
  Stripe test-mode integration). It creates a Stripe PaymentIntent per order
  (`POST /api/v1/payments`, amount/currency always re-read from order-service,
  never trusted from the client) and only calls order-service's
  `payment-authorized`/`payment-failed` callbacks from its Stripe webhook
  handler (`POST /api/v1/webhooks/stripe`) — confirmation is webhook-driven,
  not synchronous, matching Stripe's recommended pattern. Local dev needs
  `stripe listen` forwarding to that endpoint; a `marketplace-stripe-listen`
  container in the root `docker-compose.yml` runs this automatically
  (Stripe CLI's official `stripe/stripe-cli` image, authenticated via
  `--api-key` since `stripe login` doesn't work in a container) — see
  `services/payment-service/README.md`. Full scoping notes
  (including what was still undesigned before this was built, e.g. refunds)
  are in `services/order-service/docs/payment-service-scope.md`.
  auth-service was extended with a `payment-service` client-credentials
  registration (`orders:payment` scope) to support this — see the
  client-registry note above.
  Building it surfaced the same lazy-relationship class of bug again:
  `Payment.refunded_amount` read the `refunds` relationship synchronously,
  which crashes under AsyncSession unless eager-loaded. Fixed with
  `lazy="selectin"` on `Payment.refunds` (`app/models/payment.py`) — the
  same fix order-service already uses for `Order.items`. If you add a new
  relationship anywhere and read it from a plain (non-async) property or
  method, eager-load it the same way rather than relying on lazy load.
- **Shipping service now exists** (`services/shipping-service`, port 8009).
  It owns `Shipment`/`ShipmentEvent` rows (carrier, tracking number,
  manual tracking history — no real carrier integration; tracking numbers
  are entered by hand) and drives order-service's *existing*
  `POST /api/v1/internal/orders/{id}/fulfillment` callback as a shipment
  moves `pending → shipped → delivered`, mirroring exactly how
  payment-service drives `payment-authorized`/`payment-failed` without
  ever writing to Order's database directly. Creating a shipment calls
  Order's callback with `processing` *before* the local `Shipment` row is
  persisted, so a rejected transition (order not `confirmed` yet) never
  leaves an orphan shipment. A `FAILED` shipment (carrier exception) is
  recorded locally only — Order's fulfillment machine only moves forward
  and has no state for a shipping failure. auth-service was extended with
  a `shipping-service` client-credentials registration (`orders:fulfillment`
  scope) to support this — this is the fix for the "no client registered
  for `orders:fulfillment`" gap the E2E test run found earlier. Full
  scoping notes are in
  `services/order-service/docs/shipping-service-scope.md`, including the
  open question it doesn't resolve: order-service has no seller-facing
  read endpoint, so Shipping can't independently verify a seller actually
  owns line items on an order before creating a shipment for it — it
  inherits the same trust boundary Order's own fulfillment endpoint
  already has (any `orders:fulfillment`-scoped caller can advance any
  order).
- **`services/inventory-service` now has DB-backed async unit tests**
  (`tests/test_batch_reservation.py`, 14 tests) using an in-memory
  `sqlite+aiosqlite` engine, matching the fixture pattern already used in
  `services/order-service/tests/conftest.py`. `tests/conftest.py` registers
  a `@compiles(JSONB, "sqlite")` shim (test-only; production still uses real
  `JSONB` on Postgres) since sqlite has no native JSONB type. Writing these
  tests surfaced one more real bug: `reservation.expires_at` comparisons
  (`commit_reservation`, `commit_reservation_group`) assumed the DB driver
  always returns timezone-aware datetimes — true for asyncpg/Postgres, but
  not guaranteed across drivers — and would raise `TypeError` on a naive
  value instead of comparing correctly. Fixed with
  `InventoryService._is_expired()`, which treats a naive `expires_at` as
  UTC rather than crashing.
- **Notification Service source was unavailable when the integration-test
  kit was built**, so its internal route is configurable via
  `NOTIFICATION_TEST_ENDPOINT` rather than hardcoded — check
  `tests/integration-tests/integration_tests/test_40_notification.py` and
  the kit's README before assuming the endpoint path is correct.
- **`tests/integration-tests` now has cart/order/payment/shipping checkout
  workflow coverage** (`test_50_cart.py` through `test_80_shipping.py`),
  closing the gap this bullet used to describe. Writing it surfaced the
  `mark_checked_out` bug documented below.
- **Expired reservations now automatically return stock to availability**
  (fixed 2026-08-12) — closing the one item of
  `services/order-service/docs/inventory-checkout-contract.md`'s
  completion checklist that wasn't satisfied. An `inventory:expire`
  client is registered in auth-service's service-token registry
  (mirroring `inventory:sync`/`orders:payment`/`inventory:commit
  cart:checkout`), and `docker-compose.yml` now runs a Celery beat +
  worker pair for `services/inventory-service`
  (`marketplace-inventory-beat`/`-worker`, with a dedicated
  `marketplace-inventory-redis` broker) that calls
  `POST /internal/reservations/expire` on a fixed interval
  (`EXPIRE_SWEEPER_INTERVAL_SECONDS`, default 60s) using its own service
  token, via a new `AuthClient` in `app/services/auth_client.py`
  mirroring order-service's.
  Exercising the sweep endpoint for the first time (nothing had ever
  called it before) surfaced a real, previously-latent bug:
  `InventoryService.expire_reservations()` processed its whole batch in
  one transaction with a single commit at the end, so one reservation
  whose item's `reserved_quantity` had already drifted out of sync
  (violating the DB's `reserved_quantity >= 0` check) crashed the entire
  sweep — and since `list_expired_active` orders by `expires_at`, that
  poisoned row would sit first in every future run and permanently block
  expiry for every reservation behind it. Fixed by isolating each
  reservation's resolution in a savepoint (`self.session.begin_nested()`)
  so a bad row rolls back and is skipped (logged) instead of failing the
  whole batch — regression test in `tests/test_batch_reservation.py`.
- **Inventory's checkout reservation-create endpoint now requires an
  `inventory:checkout` scope** (fixed 2026-08-12). It used to be gated
  only by `Depends(get_current_principal)` — any valid JWT (buyer, seller,
  admin, or any service token) could call
  `POST /internal/checkout/reservations/batch` directly, skipping
  Cart/Order's own business rules and tying up real stock without ever
  creating an order. Fixed by defining `inventory:checkout`, registering
  it on order-service's client alongside its existing `inventory:commit
  cart:checkout`, and gating `create_reservation_batch` with
  `require_scope("inventory:checkout")`
  (`services/inventory-service/app/routes/inventory.py`).
  `/{group_id}/commit` and `/{group_id}/release` were deliberately left
  ungated beyond `AuthenticatedPrincipal` — they already have an adequate
  inline ownership check (admin, seller role, the reservation's own
  customer, or `inventory:commit` scope).
  Switching order-service to use its own service token for this call
  (instead of forwarding the buyer's JWT) surfaced a second-order bug the
  fix itself introduced: `principal.subject` is now always order-service's
  own fixed identity, not the buyer, so the reservation's `customer_id`
  and the idempotency actor (both previously derived from
  `principal.subject`) silently pointed at the wrong identity — the
  former broke a buyer's own release/cancel of their pending order with a
  live `403`, the latter would have let two different buyers' checkouts
  collide on a shared, buyer-controlled `Idempotency-Key`. Fixed by adding
  a required `customer_id: UUID` to `BatchReservationCreate`, threaded
  from order-service's own `principal.subject` through
  `BatchReservationRequest`, and used for both the reservation rows and
  the idempotency lookup instead of the calling service's identity. Full
  writeup, including why the originally-documented fix was incomplete, in
  `services/order-service/docs/inventory-checkout-contract.md`.
- **Inventory's `OutboxEvent` rows carry no correlation ID.** Unlike
  order-service's `OutboxEvent` (which has and populates a
  `correlation_id` column), inventory-service's model
  (`app/models/reliability.py`) has no such column, and
  `InventoryService._event()`'s payload dict doesn't include `request_id`
  either — even though `CorrelationIdMiddleware` already propagates
  `X-Request-ID` correctly everywhere else (forwarded by order-service on
  every call, captured on every `AuditLog` row). A future consumer of
  this outbox (nothing drains it yet) would have no way to trace an event
  back to its originating request. Fix: add `correlation_id` to
  `OutboxEvent` and thread `request_id` through `_event()`, mirroring
  order-service.
- **A buyer's cart never being retired after checkout is now fixed** (commit
  `81e3138`, "Updated the code based on testing", 2026-08-05). It used to be
  that `services/cart-service/app/routes/cart.py`'s
  `POST /internal/carts/{cart_id}/checked-out` read
  `principal.claims.get("customer_id")` from the caller's JWT and rejected
  the call if it's absent — a claim no client-credentials service token
  could ever carry, so the call always 403'd, `OrderService.create()`
  silently swallowed the failure (`except ServiceError: pass`), and every
  buyer's cart stayed `ACTIVE` forever, permanently colliding with
  order-service's `(customer_id, cart_id)` uniqueness on any second
  checkout. Fixed by moving `customer_id` into `MarkCheckedOutRequest`'s
  body instead of a JWT claim (`services/cart-service/app/schemas/cart.py`,
  `app/services/cart_service.py`) — order-service already knows it from its
  own `Order` row, and cart-service verifies it against the cart's actual
  owner column before doing anything, matching the trust pattern
  `inventory-service`'s `commit`/`release` endpoints already use (scope
  alone is sufficient authority for a trusted internal caller; the body
  value is checked, not blindly trusted). The same commit also went further
  than that fix alone required: migration `003_scope_order_cart_uq`
  replaced the plain `uq_order_customer_cart` unique constraint with a
  partial unique index scoped to non-terminal statuses
  (`WHERE status NOT IN ('CANCELLED', 'PAYMENT_FAILED')`), so a
  cancelled/failed order no longer permanently blocks reuse of that
  `(customer_id, cart_id)` pair either. Live-verified 2026-08-11 against
  the running dev stack: `tests/integration-tests`'s
  `test_checkout_reserves_stock_and_is_idempotent` passes, and the buyer's
  `GET /api/v1/cart` confirms the cart ID actually changes after checkout.
  Full writeup, including the live-verification notes, in
  `docs/e2e-platform-test-report.md`'s Finding 7.
