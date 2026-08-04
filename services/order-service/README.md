# Marketplace Order Service

FastAPI/PostgreSQL service that owns checkout order snapshots and the order lifecycle.

## Boundaries

- Auth owns users, roles, JWKS, and service tokens.
- Cart owns shopping intent and current price snapshots.
- Product owns products, variants, sellers, and prices.
- Inventory owns stock and reservations.
- Order owns immutable order/item/address snapshots and lifecycle state.
- Payment (next service) owns provider integrations, authorization, capture, and refunds.
- Notification remains internal and uses `X-Internal-API-Key`.

Order creation validates the buyer's cart, resolves seller ownership from Product,
reserves Inventory by SKU, persists the order atomically, and emits `order.created`.
The initial state is `pending_payment`.

## Run

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec order-service alembic upgrade head
curl http://localhost:8007/health
```

Or locally:

```powershell
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8007
uv run pytest -v
```

## Public API

- `POST /api/v1/orders` — buyer checkout; requires `Idempotency-Key`
- `GET /api/v1/orders` — buyer order history
- `GET /api/v1/orders/{id}` — buyer/admin order detail
- `POST /api/v1/orders/{id}/cancel` — requires `If-Match`

## Internal API

- `POST /api/v1/internal/orders/{id}/payment-authorized` — scope `orders:payment`
- `POST /api/v1/internal/orders/{id}/payment-failed` — scope `orders:payment`
- `POST /api/v1/internal/orders/{id}/payment-refunded` — scope `orders:payment`.
  `refunded_amount` is the *cumulative* amount refunded on the payment so
  far, not just the latest refund — order-service derives
  `refunded`/`partially_refunded` from that against `grand_total` rather
  than trusting a status from the caller. Only `payment_status` changes;
  `Order.status` and the Inventory reservation (already committed at
  `payment-authorized` time) are untouched.
- `POST /api/v1/internal/orders/{id}/fulfillment` — scope `orders:fulfillment`

## Required Inventory checkout contract

The current Inventory Service API reserves one `inventory_item_id` at a time,
but Cart intentionally contains SKU—not internal Inventory IDs. Do not accept an
`inventory_item_id` from the browser. Add these authenticated batch endpoints to
Inventory before the live end-to-end checkout test:

```text
POST /api/v1/internal/checkout/reservations/batch
POST /api/v1/internal/checkout/reservations/{group_id}/commit
POST /api/v1/internal/checkout/reservations/{group_id}/release
```

The full JSON contract and database rules are in
`docs/inventory-checkout-contract.md`.

## Security

Buyer and service JWTs use RS256/JWKS validation with `kid`, signature, issuer,
audience, expiry, `nbf`, and `sub`. Payment and Fulfillment callbacks additionally
require scopes. Never commit tokens or internal API keys.

Order calls Cart's `cart:checkout` endpoint (and Inventory's commit/release
endpoints, for Payment-triggered callbacks) using a short-lived service token
obtained via Identity's client-credentials grant (`ORDER_SERVICE_CLIENT_ID`/
`ORDER_SERVICE_CLIENT_SECRET`, cached in `app/auth_client.py`) — there is no
static long-lived token to configure.
