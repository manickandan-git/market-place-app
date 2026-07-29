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

`auth-service` (a.k.a. the Identity Service) is the sole authority for
credentials, roles, sessions, and JWT issuance. The other services validate
Identity-issued JWTs via JWKS and treat the token's immutable `sub` claim as
`user_id` — they never store passwords or issue tokens themselves.

## Architecture

```text
                     ┌───────────────────┐
                     │    auth-service    │  :8001
                     │  (Identity, JWKS)  │
                     └──────────┬─────────┘
                                │ validates JWT via JWKS
        ┌───────────────┬──────┴──────┬────────────────┐
        │               │             │                │
        ▼               ▼             ▼                ▼
 notification-service  user-service  product-service  inventory-service
       :8002              :8003          :8004             :8005
        │                                    │                ▲
        │ Celery worker + Redis              │ variant/SKU sync via
        ▼                                    │ PUT /internal/catalog-skus
  email delivery                             └────────────────┘
```

Inventory Service pulls product/variant projections from Product Service
(`PUT /api/v1/internal/catalog-skus/{variant_id}`) to know which SKUs it can
stock; it does not share Product Service's database.

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
(`mailpit`, profile `dev`), and all five API services. Each API container
applies its own Alembic migrations on startup.

- auth-service: http://localhost:8001/docs
- notification-service: http://localhost:8002/docs
- user-service: http://localhost:8003/docs
- product-service: http://localhost:8004/docs
- inventory-service: http://localhost:8005/docs
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

## Repository layout

```text
market-place-app/
├── docker-compose.yml       # Full local stack: all services, databases, Redis, worker
├── services/
│   ├── auth-service/        # Identity: registration, login, tokens, JWKS
│   ├── notification-service/# Email delivery, Celery worker
│   ├── user-service/        # Profiles, addresses, preferences, privacy
│   ├── product-service/     # Catalog: categories, products, variants
│   └── inventory-service/   # Warehouses, stock, reservations, movements
└── README.md
```
