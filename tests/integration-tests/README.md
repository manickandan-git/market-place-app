# Marketplace integration-test kit

This project tests the boundaries among the Marketplace services, real HTTP
calls end to end:

- Auth/Identity: RS256 access tokens and JWKS
- User: authenticated profile ownership
- Product: seller-owned products, variants and publication
- Inventory: SKU projection, stock and reservation lifecycle
- Notification: internal API-key protection
- Cart: buyer cart contents, price snapshots, checkout readiness
- Order: checkout, idempotency, cancellation, inventory reservation
- Payment: Stripe PaymentIntent creation, webhook-driven confirmation,
  refunds (partial and full) — via signed synthetic Stripe events, no
  `stripe listen` needed
- Shipping: shipment lifecycle driving Order's fulfillment callback

The tests use real HTTP calls. They do not import service code or read another
service's database.

## What you need before running

Place this folder beside your service folders, or keep it anywhere and use
the correct localhost URLs in `.env.integration`.

Start each service with its database and apply its Alembic migrations (or
just `docker compose up --build` from the repo root, which does all of
this). The workspace versions normally use these host ports:

| Service | URL |
|---|---|
| Auth | `http://localhost:8001` |
| Notification | `http://localhost:8002` |
| User | `http://localhost:8003` |
| Product | `http://localhost:8004` |
| Inventory | `http://localhost:8005` |
| Cart | `http://localhost:8006` |
| Order | `http://localhost:8007` |
| Payment | `http://localhost:8008` |
| Shipping | `http://localhost:8009` |

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

These four identities are also everything the Cart/Order/Payment/Shipping
tests need — no additional client credentials required. The
service-to-service scopes those services use on each other internally
(`orders:payment`, `inventory:commit`, `cart:checkout`, `orders:fulfillment`)
are minted by the services themselves via client-credentials grants; this
test kit only ever calls in as a buyer, seller, admin, or the inventory-sync
client, exactly like a real client would.

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

`INVENTORY_SYNC_ACCESS_TOKEN` is a short-lived (~15 minute) service token, not
a login-based value — mint one fresh before each run rather than reusing an
old paste, or every inventory-dependent test will fail with a `401` cascade
instead of the clean skip you'd get if it were simply blank:

```powershell
curl -X POST http://localhost:8001/api/v1/auth/service-token `
  -H "Content-Type: application/json" `
  -d '{"client_id":"inventory-sync-service","client_secret":"<from auth-service .env>"}'
```

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

## Step 3b: run the checkout workflow suite

```powershell
uv run pytest integration_tests/test_50_cart.py integration_tests/test_60_order.py integration_tests/test_70_payment.py integration_tests/test_80_shipping.py -m integration -v -s
```

These four files chain into one buyer journey, each building on the
previous service's public API exactly like a real client would — no
service internals are touched:

- **`test_50_cart.py`** — add/update/remove a cart item, add-item
  idempotency, checkout-readiness. Ends with an empty-but-active cart so
  downstream files start clean regardless of run order.
- **`test_60_order.py`** — checkout reserves stock and is idempotent by
  key; a second genuine checkout attempt on an already-checked-out cart is
  rejected with a clean `409 order_already_exists` rather than a `500`;
  cancelling a `pending_payment` order releases the reservation.
- **`test_70_payment.py`** — creates a real Stripe PaymentIntent (test
  mode), then signs and POSTs a synthetic `payment_intent.succeeded`/
  `payment_intent.payment_failed` webhook event directly to
  `/api/v1/webhooks/stripe` — this is what `STRIPE_WEBHOOK_SECRET` in
  `.env.integration` is for, and it must match the running
  payment-service's own secret (`docker-compose.yml` hardcodes a fixed
  dev-only value for exactly this purpose, so no `stripe listen` process
  is needed to run this suite). Confirms the order moves to
  `confirmed`/`authorized`, then exercises a partial refund followed by
  the remainder, confirming `partially_refunded` → `refunded` with
  `Order.status` left untouched throughout. A second scenario confirms a
  failed payment releases the reserved stock.
- **`test_80_shipping.py`** — on a `confirmed` order, walks a shipment
  through `pending → shipped → delivered`, confirming each step drives
  Order's `processing`/`shipped`/`delivered` fulfillment callback in
  lockstep. A second scenario confirms a carrier exception marks the
  shipment `failed` **without** calling Order back (its fulfillment
  machine only moves forward and has no state for a shipping failure).

**Known gap — cart-service never actually retires a cart after checkout**
(`mark_checked_out` requires a `customer_id` JWT claim no service token can
carry; see `CLAUDE.md`'s Known gaps and `docs/e2e-platform-test-report.md`
Finding 7 for the full writeup). Every test above that performs a checkout
depends on the `checkout_retires_cart` fixture in `conftest.py`, which
probes this once per session and `pytest.skip()`s the rest with this
explanation if it's still broken — expect `SKIPPED` rather than a `409`
pileup until that bug is fixed. This includes the very first checkout in
the suite: because the buyer persona is a fixed, reused identity across
runs, an earlier run's un-retired cart also blocks a supposedly-fresh next
run, not just later scenarios within the same run.

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

## Passing criteria

Auth/User/Product/Inventory/Notification boundary (the original gate, before
Cart Service existed):

- All health endpoints respond.
- Auth publishes a non-empty JWKS and every tested JWT contains `kid`.
- Buyer, seller, admin and sync-token claims match the agreed contract.
- User binds profiles to JWT `sub`.
- Buyer cannot use seller-only Product endpoints.
- Product owner ID comes from the seller JWT.
- Product SKU synchronizes to Inventory without duplication.
- Reservation release and commit quantities are correct.
- Overselling is rejected without stock changes.
- Notification rejects missing/wrong internal keys and accepts the correct key.

Checkout workflow (Cart/Order/Payment/Shipping):

- Cart add/update/remove and readiness all reflect current price/stock;
  add-item replay with the same `Idempotency-Key` doesn't duplicate items.
- Checkout reserves the exact quantity requested and is idempotent by key;
  a second checkout on an already-checked-out cart is rejected with `409`,
  never a `500`.
- Cancelling a `pending_payment` order fully releases the reservation.
- A webhook-confirmed payment moves the order to `confirmed`/`authorized`;
  partial then full refund moves it to `partially_refunded` then
  `refunded` without ever changing `Order.status`.
- A failed payment moves the order to `payment_failed` and releases the
  reservation.
- Each shipment step (`pending → shipped → delivered`) drives Order's
  fulfillment callback in lockstep; a shipping exception does not.
