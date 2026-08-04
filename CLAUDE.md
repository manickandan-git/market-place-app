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
across all eight services.

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
  not synchronous, matching Stripe's recommended pattern. Local dev requires
  `stripe listen --forward-to localhost:8008/api/v1/webhooks/stripe`
  running; see `services/payment-service/README.md`. Full scoping notes
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
- Per the integration-tests README, Cart Service work was meant to begin
  only after the five original services (auth/notification/user/product/
  inventory) pass the full integration suite repeatedly from a clean
  environment — cart-service and order-service were added afterward, so
  integration coverage for cart/order checkout is expected to still be
  thin/missing (`tests/integration-tests/integration_tests/` has no
  cart or order test files yet).
- **Expired reservations do not automatically return stock to
  availability** — this is the one item of
  `services/order-service/docs/inventory-checkout-contract.md`'s
  completion checklist that isn't actually satisfied.
  `InventoryItem.available_quantity` is a plain
  `on_hand_quantity - reserved_quantity` computation with no expiry
  awareness, so a reservation past its `expires_at` keeps counting
  against availability until something explicitly resolves it. The sweep
  exists (`InventoryService.expire_reservations()` behind
  `POST /internal/reservations/expire` in `services/inventory-service`,
  scoped `inventory:expire` per its own `docs/architecture.md`), but
  nothing calls it: no client is registered for `inventory:expire` in
  auth-service's service-token registry, and no
  scheduler/cron/Celery-beat invokes the endpoint anywhere in
  `docker-compose.yml` or the codebase. There's a *reactive* partial
  mitigation — `commit_reservation`/`commit_reservation_group` check
  `_is_expired()` at commit time and resolve to `EXPIRED` instead of
  committing stale stock — but that only fires if someone later tries to
  commit that specific reservation; an abandoned cart's hold otherwise
  sits locked indefinitely. To close this: register an `inventory:expire`
  client (mirroring how `inventory:sync`/`orders:payment`/
  `inventory:commit cart:checkout` were added), and add a periodic caller
  (cron container, Celery beat, or similar) that hits the sweep endpoint.
- **Inventory's checkout endpoints have no `inventory:checkout` scope —
  they aren't actually restricted to Order Service.** Verified against
  the full security/reliability checklist in
  `services/order-service/docs/inventory-checkout-contract.md`: atomic
  batch reservations, row-lock oversell prevention, idempotent
  reserve/commit/release, audit records, transactional outbox events,
  and seller/active-SKU validation are all implemented as specified, but
  `/internal/checkout/reservations/batch`, `/{group_id}/commit`, and
  `/{group_id}/release` (`services/inventory-service/app/routes/inventory.py`)
  are gated only by `Depends(get_current_principal)` — any valid JWT
  (buyer, seller, admin, or any service token) can call them, unlike
  `inventory:sync`/`inventory:expire` which are properly `require_scope`-gated.
  Practical effect: a buyer's ordinary JWT can call the batch-reserve
  endpoint directly, skipping Cart/Order's own business rules entirely,
  and tie up real stock without ever creating an order. Fix: define
  `inventory:checkout`, register it on order-service's client alongside
  its existing `inventory:commit cart:checkout`, and gate
  `create_reservation_batch` with `require_scope("inventory:checkout")`.
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
