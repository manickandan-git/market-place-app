# Marketplace Microservices

A microservices-based marketplace platform. Each service owns its own
PostgreSQL database and is independently deployable; the root
`docker-compose.yml` wires them together for local development.

## Services

| Service | Port | Responsibility | README |
|---|---|---|---|
| [auth-service](services/auth-service) | `8001` | Registration, login, email verification, password recovery, JWT/session issuance, JWKS | [README](services/auth-service/README.md) |
| [notification-service](services/notification-service) | `8002` | Transactional email delivery (verification, password reset/changed, templated/direct), Celery-backed retries | [README](services/notification-service/README.md) |
| [user-service](services/user-service) | `8003` | Buyer/seller profiles, addresses, preferences, consent, privacy/deactivation workflow | [README](services/user-service/README.md) |
| [product-service](services/product-service) | `8004` | Seller-owned product catalog, categories, variants/SKUs, public catalog reads | [README](services/product-service/README.md) |
| [inventory-service](services/inventory-service) | `8005` | Warehouses, seller stock, availability, reservations, movements, low-stock events | [README](services/inventory-service/README.md) |
| [cart-service](services/cart-service) | `8006` | Shopping intent and current price snapshots | [README](services/cart-service/README.md) |
| [order-service](services/order-service) | `8007` | Checkout order snapshots and order lifecycle | [README](services/order-service/README.md) |
| [payment-service](services/payment-service) | `8008` | Stripe payment authorization, capture, and refunds | [README](services/payment-service/README.md) |
| [shipping-service](services/shipping-service) | `8009` | Shipment records, carrier/tracking info, drives Order's fulfillment callback | [README](services/shipping-service/README.md) |
| [api-gateway](services/api-gateway) | `9000` | Reverse proxy fronting every public route: allowlisting, CORS, correlation IDs, timeouts, circuit breaker, fail-fast JWT check. No database, no business logic. | [README](services/api-gateway/README.md) |
| [assistant-service](services/assistant-service) | `8012` | Buyer-facing agentic AI chat (Claude tool-use): catalog search, availability, policy Q&A, a buyer's own orders, add/remove-cart writes. Owns no data itself. | [README](services/assistant-service/README.md) |

`services/audit-service/` and `services/search-service/` also exist but are
empty directories — no code, not yet built.

[`apps/buyer-portal`](apps/buyer-portal) is the Next.js buyer storefront. It's not a backend
service and owns no database; it talks to the gateway only from server-side
code (route handlers / Server Components), never directly from the browser.

`auth-service` (a.k.a. the Identity Service) is the sole authority for
credentials, roles, sessions, and JWT issuance. The other services validate
Identity-issued JWTs via JWKS and treat the token's immutable `sub` claim as
`user_id` — they never store passwords or issue tokens themselves.

## Architecture

`api-gateway` (`:9000`) fronts every public route into the services below
and `assistant-service` (`:8012`) calls into product/inventory/order/cart
as a read-mostly client of them — both are omitted from the diagrams below
to keep the request/data-ownership flow readable. Every service below also
validates JWTs issued by auth-service via JWKS — that fan-out is likewise
omitted:

```text
  auth-service :8001  (Identity, JWKS — issues every JWT below)

  notification-service :8002   user-service :8003
  product-service :8004        inventory-service :8005
```

The checkout chain — this is the part that actually calls between
services, beyond JWT validation:

```text
 cart-service :8006
       │ checkout (buyer reads cart snapshot via order-service)
       ▼
 order-service :8007  ───────────────►  inventory-service :8005
       ▲   ▲                            reserve / commit / release stock
       │   │                            (docs/inventory-checkout-contract.md)
       │   │
       │   └── fulfillment callback ──  shipping-service :8009
       │       (processing/shipped/     (carrier + tracking, manual —
       │        delivered)               no real carrier API yet)
       │
       └────── payment callbacks ────  payment-service :8008
               (payment-authorized/     (Stripe test mode)
                payment-failed/
                payment-refunded)
```

Order Service is the hub: it reads Cart's snapshot, resolves seller
ownership from Product, and reserves/commits/releases stock from
Inventory during checkout. Payment and Shipping own their own domains
(charges/refunds; shipments/tracking) and call *into* Order's internal
callbacks as their own state changes — Order never calls out to either of
them. Order also fires a notification on `order.created` via
notification-service.

Separately, Inventory Service pulls product/variant projections from
Product Service (`PUT /api/v1/internal/catalog-skus/{variant_id}`) to know
which SKUs it can stock; it does not share Product Service's database.

Each service has a dedicated Postgres database (and Redis where needed) started
by the root compose file; there is no cross-service database access. Service
containers reach each other over the Docker network by container name (e.g.
`marketplace-auth-service`), while host-side tooling reaches published ports
on `localhost`.

## Prerequisites

- Docker Desktop (for the full stack), or per-service: Python 3.12/3.13 and
  [uv](https://docs.astral.sh/uv/)
- PostgreSQL 16+ if running a service outside Docker

## Run the full stack

```powershell
docker compose up --build
```

This starts, in dependency order: each service's Postgres database, Redis
(auth and notification), the notification Celery worker and mailer
(`mailpit`, profile `dev`), all ten database-backed API services, the
api-gateway (no database), the observability stack (Loki/Promtail/Grafana,
dev-only), and the `apps/buyer-portal` storefront. Each API container applies its
own Alembic migrations on startup.

- auth-service: http://localhost:8001/docs
- notification-service: http://localhost:8002/docs
- user-service: http://localhost:8003/docs
- product-service: http://localhost:8004/docs
- inventory-service: http://localhost:8005/docs
- cart-service: http://localhost:8006/docs
- order-service: http://localhost:8007/docs
- payment-service: http://localhost:8008/docs
- shipping-service: http://localhost:8009/docs
- api-gateway: http://localhost:9000 (proxies the routes above under `/api/v1/*`)
- assistant-service: http://localhost:8012/docs
- apps/buyer-portal storefront: http://localhost:3001 (Docker) — run `npm run dev` in
  `apps/buyer-portal` separately for local dev on http://localhost:3000; both can be
  up at once
- mailpit (dev email capture, `--profile dev`): http://localhost:8025

Start a subset (e.g. just Identity + User):

```powershell
docker compose up --build marketplace-auth-db marketplace-auth-service marketplace-user-db marketplace-user-service
```

Stop:

```powershell
docker compose down
```

Remove all database volumes only when you intentionally want a clean slate:

```powershell
docker compose down -v
```

## Running a single service locally

Each service can also run outside Docker against its own Postgres instance;
see that service's README for `uv sync`, `.env` setup, and
`uvicorn`/Alembic commands. When reusing this compose stack's databases from
the host, use the published ports:

| Database | Host port |
|---|---|
| auth (`marketplace-auth-db`) | `5433` |
| notification (`marketplace-notification-db`) | `5434` |
| user (`marketplace-user-db`) | `5435` |
| product (`marketplace-product-db`) | `5436` |
| inventory (`marketplace-inventory-db`) | `5437` |
| cart (`marketplace-cart-db`) | `5438` |
| order (`marketplace-order-db`) | `5439` |
| payment (`marketplace-payment-db`) | `5440` |
| shipping (`marketplace-shipping-db`) | `5441` |
| assistant (`marketplace-assistant-db`) | `5442` |

## Repository layout

```text
market-place-app/
├── docker-compose.yml       # Full local stack: all services, databases, Redis, worker
├── apps/
│   └── web/                 # Next.js buyer storefront, talks to api-gateway
├── services/
│   ├── auth-service/        # Identity: registration, login, tokens, JWKS
│   ├── notification-service/# Email delivery, Celery worker
│   ├── user-service/        # Profiles, addresses, preferences, privacy
│   ├── product-service/     # Catalog: categories, products, variants
│   ├── inventory-service/   # Warehouses, stock, reservations, movements
│   ├── cart-service/        # Shopping intent, price snapshots
│   ├── order-service/       # Checkout, order lifecycle, checkout hub
│   ├── payment-service/     # Stripe authorization, capture, refunds
│   ├── shipping-service/    # Shipment records, carrier/tracking
│   ├── api-gateway/         # Reverse proxy: allowlisting, CORS, circuit breaker
│   ├── assistant-service/   # Agentic AI chat over the other services
│   ├── audit-service/       # Empty directory, not yet built
│   └── search-service/      # Empty directory, not yet built
├── tests/
│   └── integration-tests/   # Real-HTTP boundary tests across running services
└── README.md
```
