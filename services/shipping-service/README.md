# Marketplace Shipping Service

FastAPI/PostgreSQL service that owns shipment records — carrier, tracking
number, service level, and a manual tracking-event history — for orders
that have moved past payment.

## Boundaries

- Order owns order state and the fulfillment status machine
  (`pending_payment | confirmed | processing | shipped | delivered | ...`).
  Shipping never writes to Order's database — it only calls Order's
  existing internal fulfillment callback
  (`POST /api/v1/internal/orders/{id}/fulfillment`) as a shipment's own
  status advances.
- Shipping owns the `Shipment` and `ShipmentEvent` rows. There is no real
  carrier integration in this version — carrier name and tracking number
  are entered manually by the seller/admin; no label purchase, no live
  tracking API, no carrier webhook. See
  `services/order-service/docs/shipping-service-scope.md` for the full
  scoping this was built from, including open questions it doesn't
  resolve (no seller-facing order read endpoint exists yet, so Shipping
  can't independently verify seller ownership of an order before creating
  a shipment for it — it inherits the same trust boundary Order's own
  fulfillment endpoint already has).
- Auth remains the sole source of JWTs/JWKS. Shipping authenticates its
  own outbound calls to Order using a client-credentials service token
  (scope `orders:fulfillment`), fetched from
  `POST /api/v1/auth/service-token` and cached until near-expiry (see
  `app/services/auth_client.py`).

## Run

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec shipping-service alembic upgrade head
curl http://localhost:8009/health
```

Or locally:

```powershell
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8009
uv run pytest -v
```

## Shipment lifecycle

```
POST /api/v1/shipments            -> pending    (calls Order: processing)
POST /api/v1/shipments/{id}/ship      -> shipped     (calls Order: shipped)
POST /api/v1/shipments/{id}/deliver   -> delivered   (calls Order: delivered)
POST /api/v1/shipments/{id}/exception -> failed      (no Order callback)
```

`pending`/`shipped`/`delivered` are one-way and match Order's own
fulfillment sequence exactly — a shipment can't skip a step, and neither
can the Order it's attached to. `failed` is terminal and does not call
Order back: Order's fulfillment machine only ever moves forward and has no
state representing a shipping exception (lost package, carrier failure,
etc.) — that's recorded here only.

Creating a shipment calls Order's fulfillment callback with `processing`
*before* the local `Shipment` row exists — if the order isn't `confirmed`
yet (or has already moved past `processing`), Order rejects the
transition and nothing is created here either. There's never a local
Shipment that doesn't correspond to a real Order transition.

## Public API (seller/admin, JWT role `seller`/`admin`)

- `POST /api/v1/shipments` — create a shipment for an order; requires
  `Idempotency-Key`. 409s if a shipment already exists for the order (one
  shipment per order — matches Order's own whole-order, not per-line,
  fulfillment model) or if Order rejects the `processing` transition.
- `GET /api/v1/shipments/{id}` / `GET /api/v1/shipments/by-order/{order_id}`
  — fetch a shipment; 404s (not 403) for a shipment belonging to another
  seller, matching Order/Payment's convention.
- `POST /api/v1/shipments/{id}/ship` — records `carrier`/`tracking_number`,
  advances Order to `shipped`.
- `POST /api/v1/shipments/{id}/deliver` — advances Order to `delivered`.
- `POST /api/v1/shipments/{id}/exception` — records a terminal carrier
  failure locally; does not touch Order.

## What's deliberately not built yet

- Real carrier integration (label purchase, live tracking, carrier
  webhooks) — see "Boundaries" above.
- Buyer-facing tracking reads — there's no buyer-ownership check wired
  here, since Shipping has no way to confirm a buyer owns a given order
  without a new read path on order-service.
- Per-line/partial shipments for multi-seller orders — inherited from
  Order's existing whole-order fulfillment model, not a new limitation
  introduced here.
