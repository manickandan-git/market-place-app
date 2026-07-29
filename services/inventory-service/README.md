# Marketplace Inventory Service

Production-oriented FastAPI service for warehouses, seller stock, availability,
reservations, movements, and low-stock events.

## Prerequisites

- Python 3.13
- `uv`
- Docker Desktop, or PostgreSQL 17
- Running Identity Service with RS256/JWKS
- Product Service capable of publishing variant projection events

## Local setup (PowerShell)

```powershell
cd inventory-service
Copy-Item .env.example .env
uv sync
docker compose up inventory-db -d
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8005
```

Open:

- API documentation: `http://localhost:8005/docs`
- Health: `http://localhost:8005/health`

## Docker

```powershell
docker compose up --build
```

The API is available on port `8005`; PostgreSQL is exposed on `5437`.

## Validate

```powershell
uv run ruff check .
uv run pytest -q
uv run alembic upgrade head --sql
```

## Identity token expectations

Seller and customer tokens:

```json
{
  "sub": "2cd47c4d-6aa3-4f56-b65a-923de84c9312",
  "roles": ["seller"],
  "iss": "http://localhost:8001",
  "aud": "marketplace-api",
  "exp": 1785283200
}
```

Product event consumers use a short-lived service JWT with
`scope=inventory:sync`. The reservation expiration worker uses
`scope=inventory:expire`.

## Integration sequence

1. Create a warehouse as an admin.
2. Consume a Product Service variant event through
   `PUT /api/v1/internal/catalog-skus/{variant_id}`.
3. A seller creates the inventory item for that synchronized SKU.
4. The seller receives or adjusts stock.
5. Cart Service checks public availability.
6. Cart Service creates a reservation using the customer's JWT and an
   `Idempotency-Key`.
7. Order Service commits the reservation after checkout, or releases it after a
   cancellation.
8. A scheduled worker calls the expiry endpoint for abandoned reservations.

## Example requests

Set values:

```powershell
$token = "IDENTITY_JWT"
$headers = @{ Authorization = "Bearer $token" }
```

Create a warehouse:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8005/api/v1/admin/warehouses `
  -Headers $headers `
  -ContentType "application/json" `
  -Body '{"code":"ATL-01","name":"Atlanta Warehouse","is_active":true}'
```

Synchronize a Product Service SKU projection:

```powershell
$variantId = "11111111-1111-1111-1111-111111111111"
$body = @{
  product_id = "22222222-2222-2222-2222-222222222222"
  variant_id = $variantId
  seller_id = "33333333-3333-3333-3333-333333333333"
  sku = "DEMO-BLUE-M"
  is_active = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Put `
  -Uri "http://localhost:8005/api/v1/internal/catalog-skus/$variantId" `
  -Headers $headers -ContentType "application/json" -Body $body
```

Check availability:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8005/api/v1/availability/DEMO-BLUE-M?quantity=2"
```

## Important operational notes

- `If-Match` is required for mutable versioned resources and adjustments.
- `Idempotency-Key` is supported for inventory creation, adjustments, and
  reservations.
- Run reservation expiration at least once per minute in production.
- Run the outbox publisher independently; this package persists events but does
  not assume RabbitMQ or Kafka before the platform broker is selected.
- Product and Inventory databases remain separate in production.
- Notification Service is not publicly routed and continues using
  `INTERNAL_API_KEY`.

See `docs/architecture.md` for boundaries, state transitions, and events.
