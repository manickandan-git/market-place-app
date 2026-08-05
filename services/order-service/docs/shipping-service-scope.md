# Shipping Service — scope

Derived the same way `payment-service-scope.md` was: from what order-service
already exposes and assumes, not a new contract to negotiate.

## Boundary

Shipping owns shipment records — carrier, tracking number, service level,
and a manual tracking-event history. It does **not** own order state or the
fulfillment status machine (`pending_payment | confirmed | processing |
shipped | delivered | ...`) — that stays authoritative in order-service.
Shipping's job is: record what carrier is moving an order and where it's
at, and drive order-service's *existing* fulfillment transitions as that
happens. This mirrors exactly how payment-service owns charges/refunds but
never touches `Order.status` itself.

## What already exists and cannot change

`services/order-service/app/routes.py` / `app/service.py`:

- `POST /api/v1/internal/orders/{id}/fulfillment`, scope
  `orders:fulfillment`. Body: `{status, shipment_reference?, occurred_at?}`.
  Only allows `confirmed → processing → shipped → delivered`, one step at a
  time, rejecting anything out of sequence with `409`. This is the only
  endpoint Shipping calls on Order — same pattern as Payment's
  `payment-authorized`/`payment-failed`.
- No client is currently registered for `orders:fulfillment` in
  auth-service (a gap `CLAUDE.md` already documents) — Shipping Service is
  what finally needs it, exactly like Payment needed `orders:payment`.
- Order has **no seller-facing read endpoint** — `GET /api/v1/orders/{id}`
  is buyer/admin only (`Buyer = require_roles("buyer", "admin")`).
  Shipping therefore cannot independently verify that a given seller
  actually owns line items on an order before creating a shipment for it,
  and can't fetch the shipping address either. This is a pre-existing gap
  in order-service, not something Shipping can fix from its side — and
  it's the same trust boundary order-service's own fulfillment endpoint
  already has (any `orders:fulfillment`-scoped caller can advance *any*
  order; there's no per-seller check there either). Shipping inherits that
  boundary rather than pretending to close it.
- Order's fulfillment machine is whole-order, not per-line/per-seller —
  there's no way to mark only *some* items of a multi-seller order as
  shipped. Shipping's "one shipment per order" model matches this
  existing limitation; it isn't a new constraint Shipping introduces.
- Order has no state for a shipping *failure* (lost package, carrier
  exception) — the machine only goes forward. A `FAILED` shipment is
  recorded locally but does not call back to Order at all.

## What Shipping exposes

- `POST /api/v1/shipments` — seller/admin, `Idempotency-Key` required.
  Calls Order's fulfillment callback with `processing` **before**
  persisting the Shipment locally (if Order rejects the transition —
  order not `confirmed` yet, or already shipped — nothing is created here
  either). One shipment per `order_id` (unique constraint + idempotency
  key, matching Payment's `uq_payments_order_id` pattern).
- `POST /api/v1/shipments/{id}/ship` — sets `carrier`/`tracking_number`,
  calls Order's fulfillment callback with `shipped` +
  `shipment_reference=tracking_number`.
- `POST /api/v1/shipments/{id}/deliver` — calls Order's fulfillment
  callback with `delivered`.
- `POST /api/v1/shipments/{id}/exception` — records a carrier
  failure/exception locally (terminal `FAILED` status). No Order callback
  — see above.
- `GET /api/v1/shipments/{id}`, `GET /api/v1/shipments/by-order/{order_id}`,
  `GET /api/v1/shipments/{id}/events` — seller (own shipments) or admin;
  404s for a non-owner, matching Order/Payment's convention.

## Auth wiring this requires in auth-service

Same shape as Payment's `orders:payment` registration:
`SHIPPING_SERVICE_CLIENT_ID`/`SECRET`/`SUBJECT` in `Settings`, and a
`settings.shipping_service_client_id: (secret, subject, "orders:fulfillment")`
entry in `issue_service_token`'s registry.

## Explicitly out of scope for this version

- **No real carrier integration.** Per decision: carrier name and tracking
  number are entered manually by the seller/admin; no label purchase, no
  live tracking API, no carrier webhook. `ShipmentEvent` rows are
  manually created the same way (no automatic carrier-status polling).
- **No buyer-facing tracking read.** Buyers have no role check wired here
  yet; a buyer-facing "track my order" view would need either a
  buyer-ownership check against Order (which Shipping can't do without a
  new order-service read path) or a proxy endpoint added to order-service
  itself. Noted, not built.
- **No per-line/partial shipment for multi-seller orders** — see above;
  inherited from Order's existing whole-order fulfillment model.
