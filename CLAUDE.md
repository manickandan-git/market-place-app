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
user, ...) must echo those same values plus point `JWT_JWKS_URL` at
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
Order/Inventory/Product, vs. a static `INTERNAL_API_KEY` shared secret sent as
`X-Internal-API-Key` for Notification only.

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
across all seven services.

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

Newer services (cart, order) split these into packages
(`app/routes/`, `app/schemas/`, `app/models/`, `app/services/`,
`app/dependencies/`, `app/middleware/`); older services (auth, user, product,
inventory) keep them as flat modules. Follow whichever pattern the service
you're editing already uses.

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
- **Payment service does not exist yet.** order-service's README lists
  Payment as "next service" — it will own provider integrations,
  authorization, capture, and refunds. order-service already has internal
  callback routes reserved for it (`/internal/orders/{id}/payment-authorized`,
  `/internal/orders/{id}/payment-failed`, scope `orders:payment`) even
  though nothing calls them yet.
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
