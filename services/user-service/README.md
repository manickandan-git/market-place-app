# Marketplace User Service

Production-oriented FastAPI microservice for buyer/seller profiles, addresses,
preferences, notification consent, privacy workflows, audit records, and
transactional outbox events.

The Identity Service remains the authority for credentials, password recovery,
roles, sessions, and JWT issuance. This service never stores passwords or
creates login tokens. It validates the Identity JWT and uses its immutable
`sub` claim as `user_id`.

## Included

- Python 3.12/3.13, FastAPI, Pydantic v2
- SQLAlchemy 2.x async and PostgreSQL
- Alembic initial migration with indexes and append-only audit trigger
- Identity JWKS/JWT validation and buyer/seller authorization
- Profile and seller-profile APIs
- Address CRUD, soft deletion, and one-default-per-type database invariant
- User, notification, and consent preferences
- Deactivation, reactivation, export/access/correction/deletion requests
- `If-Match` optimistic concurrency and ETag responses
- idempotency records for create operations
- audit log and transactional outbox writes
- RFC-style Problem Details errors and correlation IDs
- pytest tests, Dockerfile, and Docker Compose

Kubernetes is intentionally not included in this checkpoint; local development
and Docker Compose integration come first.

## Project layout

```text
user-service/
├── alembic/                 # Migration runtime
├── app/
│   ├── dependencies/        # JWT, role, If-Match, idempotency headers
│   ├── middleware/          # Correlation ID
│   ├── models/              # SQLAlchemy domain/reliability models
│   ├── repositories/        # Data access
│   ├── routes/              # REST/OpenAPI endpoints
│   ├── schemas/             # Pydantic request/response contracts
│   ├── services/            # Transactions and business rules
│   ├── config.py
│   ├── database.py
│   ├── exceptions.py
│   └── main.py
├── docs/scope.md
├── tests/
├── .env.example
├── Dockerfile
└── pyproject.toml
```

Docker Compose for this service lives at the monorepo root
(`../../docker-compose.yml`), alongside the compose definitions for
auth-service, notification-service, and product-service.

## Prerequisites

- Python 3.12 or 3.13
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 16+ for manual local execution, or Docker Desktop
- Running Marketplace Identity Service for authenticated API requests

## Option A — Windows PowerShell local setup

Open PowerShell in the extracted `user-service` directory:

```powershell
uv sync
Copy-Item .env.example .env
```

Start only PostgreSQL:

```powershell
docker compose up -d postgres
```

Apply the schema:

```powershell
uv run alembic upgrade head
uv run alembic current
```

Start the API on port 8003:

```powershell
uv run uvicorn app.main:app --reload --port 8003
```

Open:

- Swagger UI: `http://localhost:8003/docs`
- OpenAPI: `http://localhost:8003/openapi.json`
- Liveness: `http://localhost:8003/api/v1/health/live`
- Database readiness: `http://localhost:8003/api/v1/health/ready/database`

## Option B — Docker Compose

There is no compose file inside this directory; the monorepo root
(`market-place-app/docker-compose.yml`) defines every service, including this
one's dedicated Postgres (`marketplace-user-db`). Run from the repo root:

```powershell
cd ..\..
docker compose up --build marketplace-user-db marketplace-user-service
```

Add `marketplace-auth-db marketplace-auth-service` to the same command if the
Identity Service also needs to come up, or omit the service names entirely to
start the whole stack.

The API is available at `http://localhost:8003`.

Stop:

```powershell
docker compose down
```

Remove the database volumes only when you intentionally want a clean DB:

```powershell
docker compose down -v
```

## Configuration

Copy `.env.example` to `.env`. Pydantic uses the `USER_SERVICE_` prefix for
every setting except the three JWT/identity vars below, which are aliased
to the same bare `JWT_*` names every other service uses:

```env
DATABASE_URL=postgresql+asyncpg://marketplace:marketplace@localhost:5435/user_service
JWT_ISSUER=http://localhost:8001
JWT_AUDIENCE=marketplace-api
JWT_JWKS_URL=http://localhost:8001/.well-known/jwks.json
```

The Identity access token must include:

```json
{
  "sub": "immutable-user-uuid",
  "iss": "http://localhost:8001",
  "aud": "marketplace-api",
  "roles": ["buyer", "seller"],
  "scope": "users:read users:write"
}
```

## First API calls

Store a valid Identity Service access token:

```powershell
$token = "PASTE_IDENTITY_ACCESS_TOKEN"
```

Create the local buyer profile:

```powershell
$headers = @{
  Authorization = "Bearer $token"
  "Content-Type" = "application/json"
}

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8003/api/v1/me" `
  -Headers $headers `
  -Body '{"display_name":"Demo Buyer","first_name":"Demo","last_name":"Buyer"}'
```

Read the profile:

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://localhost:8003/api/v1/me" `
  -Headers $headers
```

Create a shipping address:

```powershell
$addressHeaders = $headers.Clone()
$addressHeaders["Idempotency-Key"] = [guid]::NewGuid().ToString()

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8003/api/v1/me/addresses" `
  -Headers $addressHeaders `
  -Body '{
    "address_type":"shipping",
    "recipient_name":"Demo Buyer",
    "address_line1":"123 Main Street",
    "city":"Atlanta",
    "state_or_region":"GA",
    "postal_code":"30024",
    "country_code":"US",
    "is_default":true
  }'
```

For PATCH and DELETE requests, send the current numeric version:

```powershell
$updateHeaders = $headers.Clone()
$updateHeaders["If-Match"] = '"1"'
```

A stale version returns HTTP `412`. A missing `If-Match` returns HTTP `428`.

## Main endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/me` | Create buyer profile |
| GET/PATCH | `/api/v1/me` | Read/update buyer profile |
| PUT/GET/PATCH | `/api/v1/me/seller` | Seller profile; seller role required |
| GET | `/api/v1/sellers/{id}` | Public allowlisted seller data |
| GET/POST | `/api/v1/me/addresses` | List/create addresses |
| GET/PATCH/DELETE | `/api/v1/me/addresses/{id}` | Address operations |
| GET/PATCH | `/api/v1/me/preferences` | Locale/time-zone/currency |
| GET/PUT | `/api/v1/me/notification-preferences` | Notification consent |
| GET/PUT | `/api/v1/me/consents` | Policy/marketing decisions |
| POST | `/api/v1/me/deactivation` | Deactivate profile |
| POST | `/api/v1/me/reactivation` | Reactivate profile |
| POST | `/api/v1/me/privacy-requests` | Create export/access/deletion request |
| GET | `/api/v1/me/privacy-requests/{id}` | Retrieve owned privacy request status |

## Test and quality commands

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Verify model registration:

```powershell
uv run python -c "from app.models import Base; print(sorted(Base.metadata.tables))"
```

Expected tables:

```text
addresses, audit_logs, buyer_profiles, idempotency_records,
notification_preferences, outbox_events, privacy_requests, seller_profiles,
user_consents, user_preferences
```

## Production handoff notes

- Run the outbox publisher as a separate worker and mark events published only
  after the broker acknowledges them.
- Keep the Identity JWKS endpoint reachable and rotate keys with overlapping
  validity.
- Use a secret manager for production database credentials.
- Place the service behind TLS and an API gateway.
- Add PostgreSQL-backed API integration tests in CI.
- Configure audit/privacy retention with legal and security stakeholders.
- Add metrics/tracing and backup/restore verification before production.
- Add Kubernetes manifests only after local Identity, Notification, and User
  Service integration is stable.
