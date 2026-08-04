# Payment Service — scope, derived from the current codebase

This documents what a `payment-service` needs to be, based strictly on what
order-service, auth-service, and the rest of the stack already assume. It is
not a new contract to be negotiated (like
`inventory-checkout-contract.md`) — the two endpoints Payment must call are
already implemented and live; this is what has to be built to satisfy them.

## Boundary

Payment owns provider integration (Stripe/etc.), authorization, capture, and
refunds. It does **not** own order state, inventory, or pricing — those stay
authoritative in order-service, inventory-service, and product-service
respectively. Payment's job is: take an amount+currency it's told to charge,
attempt it against a provider, and report the outcome back.

## What already exists and cannot change without an order-service migration

`services/order-service/app/models.py`:

- `Order.payment_status`: `pending | authorized | captured | failed | refunded`
  (`PaymentStatus` enum) — Payment does not own this column, but its calls
  are what drive it from `pending` to `authorized`/`failed`.
- `Order.payment_reference: str | None` — free-text slot for the provider's
  charge/payment-intent ID. No format is enforced beyond `max_length=160`.
- `Order.grand_total: Decimal(14,2)`, `Order.currency_code: str(3)` — the
  amount Payment must charge; order-service rejects a mismatch (see below).
- `Order.status` (`OrderStatus`): checkout creates orders in
  `pending_payment`. A successful `payment-authorized` call moves it to
  `confirmed` (via `payment_authorized`) and commits the linked Inventory
  reservation group. A `payment-failed` call moves it to `payment_failed`
  and releases the reservation.

## The two endpoints Payment must call

Both are already implemented in `services/order-service/app/routes.py` /
`app/service.py`. Fixed request/response shape — do not design around
something different.

### `POST /api/v1/internal/orders/{order_id}/payment-authorized`

```json
{
  "payment_reference": "pi_...",
  "authorized_amount": "39.98",
  "currency_code": "USD"
}
```

- `authorized_amount` and `currency_code` must **exactly** equal
  `order.grand_total` / `order.currency_code`, or order-service returns
  `422 payment_amount_mismatch`. Payment must read the order's current
  total before charging (`GET /api/v1/orders/{id}` as buyer, or trust the
  amount it was handed at checkout time — see "open question" below) and
  not trust a client-supplied amount.
- Idempotent by order state: if the order is already `confirmed`, this
  returns the existing order unchanged rather than erroring or
  double-committing the Inventory reservation. Safe to retry.
- Rejects with `409 invalid_order_state` if the order isn't
  `pending_payment` (e.g., already failed, already cancelled).
- On success, order-service itself calls Inventory's
  `POST /internal/checkout/reservations/{group_id}/commit` — Payment does
  **not** talk to Inventory directly.

### `POST /api/v1/internal/orders/{order_id}/payment-failed`

```json
{
  "payment_reference": "pi_...",
  "reason": "card_declined"
}
```

- `payment_reference` optional, `reason` required (free text, 1–1000
  chars — no fixed enum, so pass through whatever the provider says).
- Idempotent the same way (already-`payment_failed` orders are a no-op).
- On success, order-service releases the Inventory reservation group
  itself.

Both require a bearer JWT with scope `orders:payment` (not a role — see
auth wiring below) and are logged/audited by order-service regardless of
outcome.

## Auth wiring this requires in auth-service

`orders:payment` is checked by `require_scope("orders:payment")` in
order-service's routes, but **no client is currently registered to receive
that scope**. auth-service's `POST /api/v1/auth/service-token` issues
scoped tokens from a hardcoded registry
(`services/auth-service/app/routes.py`, `issue_service_token`) — currently
only `inventory-sync-service` → `inventory:sync`. Payment needs the same
treatment:

1. Add `PAYMENT_SERVICE_CLIENT_ID` / `PAYMENT_SERVICE_CLIENT_SECRET` /
   `PAYMENT_SERVICE_SUBJECT` to auth-service's `Settings`
   (`app/config.py`) and `.env`/`.env.example`, mirroring
   `INVENTORY_SYNC_CLIENT_ID` etc.
2. Add an entry to the `registry` dict in `issue_service_token`:
   `settings.payment_service_client_id: (secret, subject, "orders:payment")`.
3. Payment then calls `POST /api/v1/auth/service-token` with those
   credentials to get a short-lived (15 min, per
   `SERVICE_TOKEN_EXPIRE_MINUTES`) bearer token before each call to
   order-service — same flow used to mint the `inventory:sync` token
   in this session's manual testing.

## What Payment needs to expose itself

Nothing on order-service's side calls *into* Payment — order-service only
ever receives calls. There is no message bus in this stack yet (no
Kafka/RabbitMQ; OutboxEvent tables in order-service and inventory-service
are written but nothing consumes them across service boundaries). That
means Payment's own trigger to start a charge has to come from somewhere
else — almost certainly the buyer's client application, immediately after
checkout returns an order in `pending_payment`. Payment therefore needs at
minimum:

- `POST /api/v1/payments` (or similar) — buyer-authenticated, given an
  `order_id` and a payment method reference (Stripe payment method ID,
  etc.), attempts the charge and, on the provider's response, calls back
  to order-service's two endpoints above.
- A webhook receiver for the provider (e.g. `POST /api/v1/webhooks/stripe`)
  for async outcomes (3DS confirmation, delayed captures, disputes) —
  provider-signed, not JWT-authenticated.
- Refund support (`POST /api/v1/payments/{id}/refund` or similar) is in
  scope per order-service's README ("owns provider integrations,
  authorization, capture, and refunds"). **Implemented**: Payment owns its
  own `Refund` record (full or partial, cumulative per payment) and calls
  order-service's third internal callback,
  `POST /api/v1/internal/orders/{id}/payment-refunded`, with the
  *cumulative* amount refunded so far. Order-service derives
  `refunded`/`partially_refunded` from that against `grand_total` itself
  rather than trusting a status enum from the caller — this makes a
  replayed callback with the same cumulative amount a no-op by
  construction, with no separate idempotency-key handling needed on this
  endpoint. The callback only moves `payment_status`; it does not touch
  `Order.status` or the Inventory reservation (already committed at
  `payment-authorized` time, and a refund doesn't restock).
  Payment commits its own `Refund` row and `Payment.status` change
  *before* calling this callback (the reverse of the
  `payment-authorized`/`payment-failed` webhook handlers' ordering) — the
  refund endpoint is buyer-facing and synchronous with no Stripe-driven
  retrier behind it, so committing first means a failed callback leaves
  `order.payment_status` stale (recoverable later) rather than risking a
  buyer retry re-issuing the Stripe refund (not recoverable — real money
  moving twice).

## Following existing repo conventions

Match the newest services (cart, order) rather than the older flat-module
ones — see `CLAUDE.md`'s "Per-service architecture" section:

- `app/routes/`, `app/schemas/`, `app/models/`, `app/services/`,
  `app/dependencies/`, `app/middleware/` package layout.
- `app/dependencies/auth.py`: JWT verification via `PyJWKClient` against
  auth-service's JWKS URL, `Principal` dataclass, `require_roles`/
  `require_scope` dependency factories — copy from order-service or
  cart-service verbatim, only the settings differ.
- Own Postgres database (`marketplace-payment-db`), Alembic migrations
  applied via `command: sh -c "uv run --no-sync alembic upgrade head &&
  uv run --no-sync uvicorn ... --reload"` in `docker-compose.yml`, next
  free port is **8008** (auth=8001 through order=8007 are taken).
- `Idempotency-Key` header pattern for the buyer-facing charge endpoint
  (order-service and inventory-service both use this same
  actor+key+request-hash table pattern — reuse it, don't invent a new
  one).
- `X-Internal-API-Key` is Notification's mechanism only; every other
  internal endpoint in this stack (Inventory, Order) uses scoped JWTs.
  Payment's webhook receiver is the one exception that legitimately needs
  a different scheme (provider signature verification), since a provider
  can't hold a marketplace-issued JWT.

## Open questions this scope can't resolve from code alone

- **Which provider?** Nothing in the repo picks one. Stripe is the de
  facto default for a service like this but is not implied anywhere.
- **Sync charge vs. webhook-driven confirmation** — does the buyer-facing
  `POST /api/v1/payments` call block until the provider confirms, or does
  it return "processing" and rely on the webhook to call order-service's
  callbacks? This changes the shape of the buyer-facing endpoint
  significantly and order-service's `pending_payment` state already
  supports either (it just waits for one of the two callbacks).
- **Where does the trusted charge amount come from?** Order-service's
  `grand_total` is the source of truth, but nothing currently exposes a
  buyer-scoped "get order total to charge" read path beyond the existing
  `GET /api/v1/orders/{id}`. Confirm Payment is expected to re-fetch the
  order rather than trust an amount passed from the client at checkout
  time (recommended, to avoid a client-manipulated amount).
