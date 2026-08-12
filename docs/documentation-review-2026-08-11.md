# Documentation Review — 2026-08-11

A pass over every `README.md` and `CLAUDE.md` in the repo (excluding
`node_modules`/`.venv`/`.pytest_cache`), triggered by a general "what's the
priority here" question. Two things came out of it: one finding about the
documentation itself, and a list of gaps mentioned in individual service
READMEs that root `CLAUDE.md`'s "Known gaps" section doesn't cover.

## Headline finding: the gap list can drift out of date

Root `CLAUDE.md`'s "Known gaps" section previously stated that a buyer's
cart is never retired after checkout (`mark_checked_out` always 403s). That
bug was actually fixed on 2026-08-05 (commit `81e3138`) — the doc just
hadn't been updated. This was caught by re-verifying the fix live against
the running dev stack (see `docs/e2e-platform-test-report.md`'s Finding 7
for the full trail) rather than trusting the doc at face value, and it's
now corrected in `CLAUDE.md`, that report, `tests/integration-tests/README.md`,
and the `checkout_retires_cart` fixture in
`tests/integration-tests/integration_tests/conftest.py`.

Spot-checked two other "Known gaps" entries the same way (grepped for
`inventory:checkout` scope-gating and `correlation_id` on inventory's
outbox events) — both are still genuinely unfixed, so this looks like an
isolated stale bullet rather than a systemic problem. Still, the lesson is
that a bullet in that section is a claim about the state of the code *as of
whenever it was written*, not a live fact — worth a quick grep for the
symptom before relying on one to prioritize work.

## Gaps mentioned in individual service READMEs, not in root CLAUDE.md

- **cart-service** exposes a `cart:expire` scope and
  `POST /internal/carts/expire` for sweeping abandoned carts — but, same as
  inventory's `inventory:expire` sweep (which root `CLAUDE.md` does
  document), no client is registered for that scope and nothing calls the
  endpoint on a schedule. If inventory's sweep ever gets wired up with a
  cron/Celery-beat caller, cart's should be wired up the same way at the
  same time.

- **payment-service**, from its own "what's deliberately not built yet"
  section:
  - No zero-decimal-currency support (JPY etc.) — amounts are assumed to
    have a decimal minor unit throughout.
  - No partial/manual-capture flow, only immediate full capture.
  - `charge.refund.updated` (async refund failure) webhook is unhandled —
    a refund that Stripe later fails asynchronously won't be reflected.
  - `POST /payments/{id}/refund` has **no `Idempotency-Key`** — a client
    retry on a timeout/network blip could trigger a duplicate refund at
    Stripe. Worth prioritizing given this is a real-money code path.

- **shipping-service**, from its own "what's deliberately not built yet"
  section:
  - No buyer-facing tracking read endpoint.
  - No per-line/partial shipments for multi-seller orders (a shipment is
    all-or-nothing per order today).
  - Both are blocked on the same root cause as the seller-portal's
    order-management blocker: order-service has no seller/buyer-scoped
    order-ownership read endpoint (`OrderItem.seller_id` exists and is
    indexed but nothing queries it — confirmed against source,
    `app/repository.py`, `app/service.py`, `app/models.py`).

- **user-service**, from its own "production handoff notes": the outbox
  publisher isn't a separate worker yet (runs inline), no Postgres-backed
  integration tests in CI (only SQLite unit tests), no metrics/tracing, no
  k8s manifests (this last one is a deliberate deferral, not an oversight).

- **api-gateway**: no rate limiting implemented at all. Its own docs note
  that if it's added, it needs Redis-backed shared state since the gateway
  may run more than one replica. Also, its own docs confirm that
  inventory's missing `inventory:checkout` scope (already tracked in root
  `CLAUDE.md`) is only a partial mitigation at the gateway layer — the
  gateway blocks *public* access to those routes, but any authenticated
  caller inside the Docker network can still reach them directly.

- **apps/buyer-portal**: its `README.md`/`AGENTS.md` are still unmodified
  Next.js boilerplate — no project-specific documentation exists for this
  app at all, unlike every backend service's detailed README. Not a code
  gap, just a documentation gap, but worth closing given how much
  narrative detail the backend READMEs carry.

- **apps/seller-portal** (planning doc, not yet implemented): confirms
  with source citations that order-service's missing seller-order-read
  endpoint (see shipping-service bullet above) is the concrete blocker for
  its Phase 1 "Order management" feature. Two open decisions noted in that
  doc, unrelated to backend gaps: token storage strategy (undecided), and
  whether seller onboarding (`POST /me/seller`) belongs in this app or
  elsewhere.

## Explicitly out of scope, not a bug

The integration test suite's payment/shipping tests (`test_70`, `test_80`)
currently fail locally with `400 invalid_webhook_signature` on
`POST /api/v1/webhooks/stripe`. This is expected friction, not a new
finding: `docker-compose.yml` (around the `marketplace-payment-service`
block) documents that `services/payment-service/.env`'s
`STRIPE_WEBHOOK_SECRET` needs to be temporarily switched to the fixed
`whsec_dev_only_e2e_workflow_test_secret` value before running the
integration suite, and switched back to the live `stripe listen` session's
secret afterward. It was left at the live value (needed for the running
`marketplace-stripe-listen` container) during this review, which is why
those two tests failed here — not touched, since flipping it would have
broken the live Stripe listener the running stack depends on.

## Suggested next priorities

Unchanged from before this review, since the cart-retirement bug is now
confirmed fixed rather than pending:

1. **order-service seller-order read endpoint** — unblocks both
   shipping-service's buyer-tracking gap and seller-portal's entire
   Phase 1 order-management feature. Highest leverage if seller-portal
   work is imminent.
2. **`inventory:checkout` scope gating** — cheap, closes a real internal
   authorization gap (`services/inventory-service/app/routes/inventory.py`).
3. **Refund `Idempotency-Key`** — cheap, closes a real-money double-refund
   risk in payment-service.
4. **`cart:expire` / `inventory:expire` scheduler** — both sweep endpoints
   exist; neither has a caller. Worth wiring up together rather than
   fixing one and leaving the other.
