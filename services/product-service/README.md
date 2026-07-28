# Marketplace Product Service

Production-oriented FastAPI service for seller-managed product catalog data and
public catalog reads.

## Implemented scope

- Hierarchical categories managed by administrators
- Seller-owned products with draft, active, inactive, and archived states
- Product variants/SKUs, prices, currency, attributes, barcode, and weight
- Product image references with deterministic ordering
- Public catalog listing and product-detail endpoints
- Seller and administrator authorization
- RS256 JWT verification through Identity Service JWKS
- Validation of `kid`, algorithm, signature, issuer, audience, expiry, not-before,
  and immutable `sub`
- Optimistic concurrency through `If-Match`
- Idempotent product creation through `Idempotency-Key`
- Audit records and transactional outbox events
- PostgreSQL, SQLAlchemy 2 async, Alembic, Docker, and Pytest

Inventory quantities are deliberately not stored here. The upcoming Inventory
Service will own available, reserved, and safety-stock quantities by SKU.
Product media bytes are also external; this service stores secure HTTPS
references only.

## Security contract

Identity Service signs access tokens with RS256 and publishes public keys:

```env
JWT_JWKS_URL=http://localhost:8001/.well-known/jwks.json
JWT_ISSUER=http://localhost:8001
JWT_AUDIENCE=marketplace-api
JWT_ALGORITHMS=["RS256"]
```

Write APIs require `seller` or `admin`. Category mutation requires `admin`.
Ownership always comes from JWT `sub`; the API never accepts an owner user ID.
The Notification Service remains internal and is not called by this service in
the Product Service MVP.

## Local setup (PowerShell)

Prerequisites: Python 3.13, `uv`, and Docker Desktop.

This service does not have its own `docker-compose.yml` — the repo root
`docker-compose.yml` is the single source of truth for the whole stack (same
as `auth-service`, `notification-service`, and `user-service`).

```powershell
cd product-service
Copy-Item .env.example .env
uv sync
docker compose -f ..\..\docker-compose.yml up -d marketplace-product-db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8004
```

Open:

- Swagger UI: `http://localhost:8004/docs`
- Health: `http://localhost:8004/health`
- OpenAPI: `http://localhost:8004/openapi.json`

Ensure Identity (auth-service) runs at `http://localhost:8001`, or adjust the
three JWT environment settings to match its issuer and JWKS endpoint.

## Run the complete container

From the repo root, bring up the whole stack (or just this service and its
dependencies):

```powershell
docker compose up --build marketplace-product-service
```

`marketplace-product-service` is reachable on host port `8004`; inside the
Docker network it talks to `marketplace-auth-service:8001` for JWKS.

## Seed a category

Obtain an Identity access token containing the `admin` role:

```powershell
$token = "PASTE_ADMIN_ACCESS_TOKEN"
$headers = @{ Authorization = "Bearer $token" }
$body = @{
  name = "Electronics"
  slug = "electronics"
  description = "Consumer electronics"
  sort_order = 10
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8004/api/v1/admin/categories" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

## Create and publish a product

Use a seller token and replace `CATEGORY_ID`:

```powershell
$token = "PASTE_SELLER_ACCESS_TOKEN"
$headers = @{
  Authorization = "Bearer $token"
  "Idempotency-Key" = "keyboard-create-001"
}
$body = @{
  category_id = "CATEGORY_ID"
  name = "Mechanical Keyboard"
  slug = "mechanical-keyboard"
  short_description = "Hot-swappable mechanical keyboard"
  brand = "Marketplace Demo"
  attributes = @{ layout = "75%"; connectivity = "USB-C" }
  variants = @(
    @{
      sku = "KB-75-BLK"
      name = "Black"
      price_amount = 89.99
      compare_at_price = 109.99
      currency_code = "USD"
      attributes = @{ color = "black"; switch = "brown" }
      is_active = $true
    }
  )
  images = @(
    @{
      url = "https://example.com/products/keyboard-black.jpg"
      alt_text = "Black mechanical keyboard"
      sort_order = 0
    }
  )
} | ConvertTo-Json -Depth 8

$product = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8004/api/v1/seller/products" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body

$publishHeaders = @{
  Authorization = "Bearer $token"
  "If-Match" = "$($product.version)"
}
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8004/api/v1/seller/products/$($product.id)/status" `
  -Headers $publishHeaders `
  -ContentType "application/json" `
  -Body '{"status":"active"}'
```

Public reads do not require a token:

```powershell
Invoke-RestMethod "http://localhost:8004/api/v1/products"
```

## Endpoint summary

| Method | Route | Access |
|---|---|---|
| GET | `/health`, `/ready` | Public/infrastructure |
| GET | `/api/v1/categories` | Public |
| POST/PATCH | `/api/v1/admin/categories...` | Admin |
| GET | `/api/v1/products` | Public active catalog |
| GET | `/api/v1/products/{id}` | Public active product |
| GET | `/api/v1/products/by-slug/{slug}` | Public active product |
| GET/POST/PATCH | `/api/v1/seller/products...` | Seller/Admin |
| PUT | `/api/v1/seller/products/{id}/status` | Owner/Admin |
| POST/PATCH | `/api/v1/seller/products/{id}/variants...` | Owner/Admin |
| POST/DELETE | `/api/v1/seller/products/{id}/images...` | Owner/Admin |

The API Gateway should expose the public and seller catalog routes, validate
edge policies, and forward the bearer token. Product Service still performs its
own authorization and ownership enforcement.

## Quality checks

```powershell
uv run ruff check .
uv run pytest -q
uv run alembic upgrade head --sql
uv run python -c "from app.main import app; print(len(app.openapi()['paths']))"
```

## Event contract

Outbox event names:

- `catalog.product.created.v1`
- `catalog.product.updated.v1`
- `catalog.product.active.v1`
- `catalog.product.inactive.v1`
- `catalog.product.archived.v1`
- `catalog.product.variant_changed.v1`
- `catalog.product.image_changed.v1`

The outbox publisher and RabbitMQ/Kafka broker are intentionally deferred until
the shared event-broker milestone. Consumers must use the event ID as their
idempotency key.

## Recommended next integration test

1. Create an administrator category through the gateway.
2. Create a product with a seller JWT.
3. Verify another seller receives `404` (not `403` — ownership and
   not-found are indistinguishable by design, to avoid leaking which IDs
   exist to non-owners).
4. Publish with the current `If-Match` version.
5. Confirm public reads return active products only.
6. Confirm invalid issuer/audience/signature/unknown `kid` tokens fail.
7. Confirm audit and outbox rows are committed with the catalog transaction.

