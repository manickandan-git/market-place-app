# Marketplace integration-test kit

This project tests the boundaries among the completed Marketplace services:

- Auth/Identity: RS256 access tokens and JWKS
- User: authenticated profile ownership
- Product: seller-owned products, variants and publication
- Inventory: SKU projection, stock and reservation lifecycle
- Notification: internal API-key protection

The tests use real HTTP calls. They do not import service code or read another
service's database.

## What you need before running

Place this folder beside your five service folders, or keep it anywhere and use
the correct localhost URLs in `.env.integration`.

Start each service with its database and apply its Alembic migrations. The
workspace versions normally use these host ports:

| Service | URL |
|---|---|
| Auth | `http://localhost:8001` |
| User | `http://localhost:8003` |
| Product | `http://localhost:8004` |
| Inventory | `http://localhost:8005` |
| Notification | `http://localhost:8002` (change if needed) |

All services that verify a user JWT must use the same issuer and audience. The
issuer value in `.env.integration` must exactly equal the `iss` claim in the
token—even a hostname change from `localhost` to `identity-service` matters.

## Step 1: create test identities

Create these Auth Service users/clients:

| Identity | Required role/scope |
|---|---|
| Buyer | `buyer` role |
| Seller A | `seller` role |
| Seller B | `seller` role; optional until cross-seller tests are added |
| Admin | `admin` role |
| Inventory Sync client | `inventory:sync` scope |

Use short-lived tokens only. Do not commit them.

The Inventory Sync token is not the Notification Service API key. Inventory's
internal SKU endpoint is JWT-protected with `inventory:sync`; Notification is
the service that remains protected by `INTERNAL_API_KEY`.

## Step 2: configure the tests

In PowerShell:

```powershell
cd marketplace-integration-tests
Copy-Item .env.integration.example .env.integration
notepad .env.integration
```

The simplest setup is to paste these five short-lived tokens:

```env
BUYER_ACCESS_TOKEN=...
SELLER_A_ACCESS_TOKEN=...
ADMIN_ACCESS_TOKEN=...
INVENTORY_SYNC_ACCESS_TOKEN=...
```

`SELLER_B_ACCESS_TOKEN` is reserved for cross-seller authorization scenarios.

Alternatively, leave the buyer/seller/admin tokens blank and configure the test
email/password values. The suite will call `AUTH_LOGIN_PATH`. If your login
request uses `username` instead of `email`, change:

```env
AUTH_LOGIN_EMAIL_FIELD=username
```

If your login response nests the token or uses a form body, update only
`integration_tests/auth.py`; that file is the Auth adapter.

## Step 3: run the Product–Inventory test first

```powershell
uv sync
uv run pytest integration_tests/test_30_product_inventory.py -m integration -v -s
```

This test performs the complete sequence:

1. Admin creates a category.
2. Seller creates and activates a product with a SKU.
3. The SKU is delivered to Inventory's internal projection endpoint.
4. Replaying the SKU event proves projection idempotency.
5. Admin creates a warehouse.
6. Seller adds 100 units.
7. Buyer reserves and releases 5 units.
8. Buyer reserves and commits another 5 units.
9. Final inventory is `on_hand=95`, `reserved=0`, `available=95`.
10. An oversell attempt is rejected without changing stock.

The direct call to `/internal/catalog-skus` represents event delivery. When you
add RabbitMQ or Kafka, replace that call with publishing the Product outbox event
and wait until Inventory's projection appears.

## Step 4: run the complete suite

```powershell
./run-integration.ps1
```

Equivalent command:

```powershell
uv run pytest -m integration -v
```

To run the tests from Docker while the services run on Windows, replace every
service URL in `.env.integration` with `http://host.docker.internal:<port>`, then:

```powershell
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

## Notification adapter

The Notification Service source was not available when this kit was produced,
so its creation route is intentionally configurable. Set:

```env
NOTIFICATION_TEST_ENDPOINT=/your/real/internal/notification/route
INTERNAL_API_KEY=your-integration-key
```

If its JSON request differs, edit `_payload()` in
`integration_tests/test_40_notification.py`. Until the endpoint is configured,
only the Notification tests skip; health and the other service tests still run.

## Common failures

### `401 Invalid or expired access token`

Check token expiration, `kid`, JWKS URL, issuer and audience. The `JWT_ISSUER`
configured in this kit and in User/Product/Inventory must match the token `iss`
exactly.

### `403 role required`

Confirm Auth emits `roles: ["seller"]` or `roles: ["admin"]`. Product and
Inventory accept either `roles` or `role`.

### `403 inventory:sync scope required`

Use a service token containing `scope: "inventory:sync"`. A seller token is not
enough for the internal catalog projection endpoint.

### Product test returns `422 invalid_category`

The admin category creation probably failed or the Admin token lacks the
`admin` role. Run with `-s` and inspect the readable response included in the
failure.

### Services are healthy but token verification fails in Docker

Do not mix the issuer embedded in the token with the JWKS network address. A
service may retrieve JWKS from `http://auth-service:8000/...` while still
validating an issuer such as `http://localhost:8001`, provided that exact issuer
is what Auth placed in `iss`.

## Passing criteria before Cart Service

- All five health endpoints respond.
- Auth publishes a non-empty JWKS and every tested JWT contains `kid`.
- Buyer, seller, admin and sync-token claims match the agreed contract.
- User binds profiles to JWT `sub`.
- Buyer cannot use seller-only Product endpoints.
- Product owner ID comes from the seller JWT.
- Product SKU synchronizes to Inventory without duplication.
- Reservation release and commit quantities are correct.
- Overselling is rejected without stock changes.
- Notification rejects missing/wrong internal keys and accepts the correct key.

After these pass repeatedly from a clean environment, begin Cart Service.
