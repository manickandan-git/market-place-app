# Marketplace Payment Service

FastAPI/PostgreSQL service that owns provider (Stripe) payment authorization,
capture, and refunds for the marketplace checkout flow.

## Boundaries

- Order owns order state, totals, and the checkout lifecycle. Payment never
  writes to Order's database — it only calls Order's two internal callback
  endpoints and re-reads `grand_total`/`currency_code` from Order before
  charging, so a client can never manipulate the charged amount.
- Payment owns the Stripe PaymentIntent per order, refunds, and the webhook
  event log. It does not own inventory reservations — Order commits/releases
  those itself in response to Payment's callbacks.
- Auth remains the sole source of JWTs/JWKS. Payment authenticates its own
  outbound calls to Order using a client-credentials service token (scope
  `orders:payment`), fetched from `POST /api/v1/auth/service-token` and
  cached until near-expiry (see `app/services/auth_client.py`).

There is no message bus in this stack. Order never calls into Payment —
the buyer's client is what triggers `POST /api/v1/payments` after checkout
returns an order in `pending_payment`. See
`services/order-service/docs/payment-service-scope.md` for the full scoping
this was built from, including open questions this implementation resolves
(webhook-driven confirmation, order as the amount source of truth).

## Run

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec payment-service alembic upgrade head
curl http://localhost:8008/health
```

Or locally:

```powershell
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8008
uv run pytest -v
```

## Stripe test-mode setup (development)

1. Create a free Stripe account, switch to **test mode**, and copy the
   test **Secret key** (`sk_test_...`) from
   https://dashboard.stripe.com/test/apikeys into `STRIPE_SECRET_KEY` in
   `services/payment-service/.env`.
2. `docker compose up -d` (or just `marketplace-stripe-listen`) starts the
   [Stripe CLI](https://docs.stripe.com/stripe-cli) `stripe listen`
   automatically, in its own container
   (`marketplace-stripe-listen` in the root `docker-compose.yml`) —
   forwarding real Stripe test-mode webhook events straight to
   `payment-service`. No public URL, ngrok, or host-side `stripe` install
   needed, and unlike running it on your host it doesn't stop when you
   close a terminal. It authenticates with `STRIPE_SECRET_KEY` directly
   (`--api-key`, since `stripe login` doesn't work in a container), so it
   picks up the same key you just set in step 1.

   The only manual step is the webhook signing secret, and only once: it
   doesn't change between `stripe listen` restarts, so run
   `docker compose logs -f marketplace-stripe-listen`, copy the
   `whsec_...` from the "Ready! ... Your webhook signing secret is
   whsec_..." line into `STRIPE_WEBHOOK_SECRET`, then
   `docker compose up -d marketplace-payment-service` to pick it up. A
   payment can't resolve out of `pending` until this is running and
   correct, since confirmation is webhook-driven (see below).

   Running `stripe listen` on your host instead is still fine if you
   prefer it (`stripe listen --forward-to localhost:8008/api/v1/webhooks/stripe`)
   — just stop the `marketplace-stripe-listen` container first so the two
   don't both try to deliver the same events.
3. Use Stripe's test card numbers to exercise both outcomes:
   `4242 4242 4242 4242` (any future expiry, any CVC) always succeeds;
   `4000 0000 0000 0002` always declines.

No real money moves while using test-mode keys. Switching to production
later is just swapping `sk_test_...`/`whsec_...` for live values —
nothing else about the integration changes.

## Confirmation flow

`POST /api/v1/payments` only **creates** a Stripe PaymentIntent and returns
its `client_secret` — it does not charge anything itself, and it does not
call Order's callbacks. The buyer's client must confirm the PaymentIntent
client-side (`stripe.confirmCardPayment(client_secret)` via Stripe.js/
Elements, or an equivalent mobile SDK). Stripe then delivers
`payment_intent.succeeded` or `payment_intent.payment_failed` to this
service's webhook, which is the only place that calls Order's
`payment-authorized`/`payment-failed` endpoints. This is the
Stripe-recommended pattern: webhooks are authoritative because a client can
disappear mid-confirmation (closed tab, 3DS redirect, flaky network) and
the webhook still arrives.

## Public API (buyer, JWT role `buyer`/`admin`)

- `POST /api/v1/payments` — create a PaymentIntent for an order; requires
  `Idempotency-Key`. 409s if a payment already exists for the order or the
  order isn't `pending_payment`.
- `GET /api/v1/payments/{id}` — fetch payment status; 404s (not 403) for a
  payment that belongs to another customer, matching Order's convention.
- `POST /api/v1/payments/{id}/refund` — full or partial refund of a
  succeeded payment. `amount` omitted refunds whatever remains. On success,
  calls order-service's `payment-refunded` callback with the *cumulative*
  amount refunded on the payment so far (not just this refund), so
  `Order.payment_status` moves to `refunded`/`partially_refunded` the same
  way regardless of how many partial refunds preceded it. The refund and
  local `Payment.status` change are committed *before* that callback runs
  — if the callback fails, `Order.payment_status` is left stale rather
  than risking a client retry re-issuing the (non-idempotent) Stripe
  refund call.

## Webhook (Stripe, signature-verified — not JWT)

- `POST /api/v1/webhooks/stripe` — verified via `Stripe-Signature` against
  `STRIPE_WEBHOOK_SECRET`. Idempotent by Stripe event ID
  (`webhook_events` table) since Stripe delivers at-least-once.

## What's deliberately not built yet

- Zero-decimal currencies (JPY, etc.) — `to_minor_units`/`from_minor_units`
  in `app/services/stripe_client.py` assume 2-decimal currencies.
- Partial-capture / manual-capture flows — every PaymentIntent is created
  with Stripe's default automatic capture.
- Refund failure handling beyond a synchronous Stripe API error — Stripe
  refunds can also fail asynchronously via webhook
  (`charge.refund.updated`), which isn't handled yet.
- `Idempotency-Key` on `POST /api/v1/payments/{id}/refund` — unlike
  `POST /api/v1/payments`, the refund endpoint doesn't dedupe retries, and
  `stripe.create_refund` isn't called with an idempotency key either. A
  client retry after a dropped response could issue a second real refund
  at Stripe. Deferred as a separate hardening task rather than folded into
  the order-service refund callback.
