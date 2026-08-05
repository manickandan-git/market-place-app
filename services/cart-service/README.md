# Marketplace Cart Service

Production-oriented FastAPI service for authenticated and guest shopping carts.
It follows the security and service boundaries used by the existing Auth, User,
Product, and Inventory services.

## Features

- One active cart per authenticated buyer
- Opaque guest carts and login-time merge
- Add, update, remove, clear, and saved-for-later operations
- Product and price snapshots from Product Service
- Inventory availability checks without reserving stock
- Checkout-readiness validation and price refresh
- JWKS validation for buyer and internal service JWTs
- Optimistic concurrency with `If-Match-Version`
- Add-item idempotency with `Idempotency-Key`
- Cart expiration workflow
- Audit logs and transactional outbox events
- PostgreSQL, Alembic, Docker, tests, and OpenAPI

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
| Cart PostgreSQL | 5438 |

Adjust the ports in `.env` if your current service layout differs.

## Start locally with PowerShell

```powershell
Copy-Item .env.example .env
uv sync
docker compose up -d cart-db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8006
```

Open:

```text
http://localhost:8006/docs
http://localhost:8006/health
http://localhost:8006/ready
```

Run tests:

```powershell
uv run pytest -v
uv run ruff check app tests alembic
```

## Required configuration

```env
DATABASE_URL=postgresql+asyncpg://marketplace:marketplace@localhost:5438/cart_service
JWT_JWKS_URL=http://localhost:8001/.well-known/jwks.json
JWT_ISSUER=http://localhost:8001
JWT_AUDIENCE=marketplace-api
PRODUCT_SERVICE_URL=http://localhost:8004
INVENTORY_SERVICE_URL=http://localhost:8005
```

The `JWT_ISSUER` value must exactly match the `iss` claim in Auth Service tokens.
Buyer access tokens should contain a UUID `sub`. Order Service tokens will need
`cart:checkout`; a scheduler token will need `cart:expire`.

## API summary

| Method and path | Purpose | Authentication |
|---|---|---|
| `POST /api/v1/guest-carts` | Create guest cart and return token once | Public |
| `GET /api/v1/cart` | Get/create current cart | JWT or cart token |
| `POST /api/v1/cart/items` | Add SKU snapshot | JWT or cart token |
| `PATCH /api/v1/cart/items/{id}` | Change quantity | JWT or cart token |
| `DELETE /api/v1/cart/items/{id}` | Remove item | JWT or cart token |
| `POST /api/v1/cart/items/{id}/save-for-later` | Save an item | JWT or cart token |
| `POST /api/v1/cart/saved-items/{id}/move-to-cart` | Restore saved item | JWT or cart token |
| `POST /api/v1/cart/readiness` | Refresh prices and check stock | JWT or cart token |
| `POST /api/v1/cart/merge` | Merge guest cart after login | JWT |
| `DELETE /api/v1/cart` | Clear active items | JWT or cart token |
| `POST /api/v1/internal/carts/{id}/checked-out` | Close cart after order | `cart:checkout` |
| `POST /api/v1/internal/carts/expire` | Expire due carts | `cart:expire` |

All cart mutation requests require the current aggregate version:

```http
If-Match-Version: 1
```

Add-item also supports:

```http
Idempotency-Key: unique-request-key-0001
```

Guest calls use the token returned by `POST /guest-carts`:

```http
X-Cart-Token: opaque-token-value
```

## Example buyer flow

```powershell
$headers = @{
  Authorization = "Bearer $env:BUYER_ACCESS_TOKEN"
}

$cart = Invoke-RestMethod `
  -Uri http://localhost:8006/api/v1/cart `
  -Headers $headers

$headers["If-Match-Version"] = "$($cart.version)"
$headers["Idempotency-Key"] = "cart-add-$(New-Guid)"

$body = @{
  product_id = "PRODUCT_UUID"
  variant_id = "VARIANT_UUID"
  quantity = 2
} | ConvertTo-Json

$cart = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8006/api/v1/cart/items `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body

$headers["If-Match-Version"] = "$($cart.version)"
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8006/api/v1/cart/readiness `
  -Headers $headers
```

## Integration assumptions

Product Service must expose `GET /api/v1/products/{product_id}` with variants
and images. Inventory Service must expose
`GET /api/v1/availability/{sku}?quantity=N`.

Cart Service never reads another service's database and never sends an inventory
adjustment or reservation request. See `docs/architecture.md` for the complete
boundary and checkout handoff.
