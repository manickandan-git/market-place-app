# API Gateway route allowlist

The gateway proxies **only** the routes explicitly marked `PUBLIC` below.
Everything else — every `/internal/...` path, plus a couple of paths that
aren't prefixed `/internal` but are equally not meant for end users — is
`BLOCKED`: the gateway must not register a proxy route for it at all (404,
not "proxy it but check a role"), so a gap in per-service scope/role
enforcement doesn't become internet-reachable just because the gateway
exists.

This is a snapshot derived from reading each service's route definitions
directly (`app/routes*.py` / `app/routes/*.py`) on 2026-08-05, not from
service READMEs, which occasionally lag the code. Re-derive from source
before trusting this for a service that has changed since.

Downstream services still perform their own JWT validation and
role/ownership authorization — see the "why" for that in the parent
conversation. The gateway's checks here are edge policy (defense in depth
and reduced attack surface), not a replacement for service-level auth.

## Rule of thumb used below

- Any path segment literally starting `internal/` → `BLOCKED`. These are
  only ever called service-to-service, over the Docker network, using a
  scoped service JWT (`inventory:sync`, `orders:payment`,
  `orders:fulfillment`, `cart:checkout`, `cart:expire`, `inventory:expire`)
  or, for notification-service, a static `X-Internal-API-Key`. No end user
  JWT is ever meant to reach them.
- `/service-token` (auth-service) → `BLOCKED`. It's a client-credentials
  exchange for trusted service callers (`client_id`/`client_secret`); no
  legitimate browser/mobile caller needs it, and exposing it externally is
  pure added attack surface (credential-stuffing target) for zero benefit.
- `/health`, `/live`, `/ready*` → `BLOCKED` from the gateway's public
  surface. These are container-orchestration probes (Docker/k8s), not an
  end-user API; the gateway should have its own `/health` rather than
  fanning out to every downstream service's.
- `POST /webhooks/stripe` (payment-service) → `PUBLIC`, but **treated
  specially**: it's called by Stripe, not by an end user, so it carries no
  bearer JWT at all. The gateway's edge-level `TokenVerifier` (see
  `app/services/token_verifier.py`) only runs when a request carries an
  `Authorization: Bearer ...` header, so this path is exempted from it
  automatically, with no special-case code needed — same for any
  request-body size assumptions, since Stripe signs the raw body and the
  gateway must not alter it in transit.
- Everything else defaults to `PUBLIC` and relies on the service's own
  `require_roles(...)` / `require_scope(...)` / ownership checks.

## auth-service (`:8001`, prefix `/api/v1` unless noted)

Corrected from an earlier pass of this doc: `routes.py` mounts under
`prefix="/auth"`, `user_routes.py` under `prefix="/users"`, and
`session_routes.py` under `prefix="/auth/sessions"` — so these are `/auth/*`
and `/users/*`, not bare `/register`, `/me`, etc. That also means there's
**no actual collision** with user-service's `/api/v1/me*` routes below
(different first segment), which an earlier draft of this doc wrongly
implied.

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/.well-known/jwks.json` | PUBLIC | no prefix; every service's JWKS fetch also needs this reachable, but they hit auth-service directly over the Docker network, not through the gateway — expose anyway since browsers may need it for client-side verification tooling |
| POST | `/auth/register` | PUBLIC | |
| POST | `/auth/verify-email` | PUBLIC | |
| POST | `/auth/resend-verification` | PUBLIC | |
| POST | `/auth/login` | PUBLIC | |
| POST | `/auth/token` | PUBLIC | |
| POST | `/auth/service-token` | **BLOCKED** | client-credentials grant for trusted services only |
| POST | `/auth/refresh` | PUBLIC | |
| POST | `/auth/logout` | PUBLIC | |
| POST | `/auth/forgot-password` | PUBLIC | |
| POST | `/auth/reset-password` | PUBLIC | |
| POST | `/auth/change-password` | PUBLIC | |
| GET | `/auth/sessions` | PUBLIC | list current user's sessions |
| DELETE | `/auth/sessions/{session_id}` | PUBLIC | session revocation, user-facing |
| GET | `/users/me` | PUBLIC | auth identity profile — distinct from user-service's richer `/me` buyer/seller profile |
| GET | `/users/me/audit-events` | PUBLIC | |

## user-service (`:8003`, prefix `/api/v1`)

| Method | Path | Status |
|---|---|---|
| POST/GET/PATCH | `/me`, `/me/seller` | PUBLIC |
| GET | `/sellers/{seller_id}` | PUBLIC |
| POST | `/me/deactivation`, `/me/reactivation` | PUBLIC |
| POST/GET | `/me/privacy-requests*` | PUBLIC |
| GET/PATCH | `/me/preferences` | PUBLIC |
| GET/PUT | `/me/notification-preferences` | PUBLIC |
| GET/PUT | `/me/consents` | PUBLIC |
| GET/POST/PATCH/DELETE | `/me/addresses*` | PUBLIC |

No internal-only routes defined in this service today.

## product-service (`:8004`, prefix `/api/v1`)

| Method | Path | Status |
|---|---|---|
| GET | `/categories` | PUBLIC |
| POST/PATCH | `/admin/categories*` | PUBLIC (admin role enforced downstream) |
| GET | `/products`, `/products/{id}`, `/products/by-slug/{slug}` | PUBLIC |
| GET/POST/PATCH/PUT/DELETE | `/seller/products*` | PUBLIC (seller/admin + ownership enforced downstream) |

No internal-only routes defined in this service today.

## inventory-service (`:8005`, prefix `/api/v1`)

| Method | Path | Status | Notes |
|---|---|---|---|
| GET | `/availability/{sku}` | PUBLIC | |
| PUT | `/internal/catalog-skus/{variant_id}` | **BLOCKED** | scope `inventory:sync`, called by product-service |
| GET/POST/PATCH | `/admin/warehouses*` | PUBLIC | admin role enforced downstream |
| GET/POST/PATCH | `/seller/inventory*` | PUBLIC | seller/admin + ownership enforced downstream |
| POST | `/reservations` | PUBLIC | any authenticated principal today |
| GET | `/reservations` | PUBLIC | |
| POST | `/reservations/{id}/commit`, `/reservations/{id}/release` | PUBLIC | |
| POST | `/internal/checkout/reservations/batch` | **BLOCKED** | ⚠️ see below |
| POST | `/internal/checkout/reservations/{group_id}/commit` | **BLOCKED** | ⚠️ see below |
| POST | `/internal/checkout/reservations/{group_id}/release` | **BLOCKED** | ⚠️ see below |
| POST | `/internal/reservations/expire` | **BLOCKED** | scope `inventory:expire` |

⚠️ The three checkout-batch routes are exactly the ones CLAUDE.md flags as
missing their `inventory:checkout` scope gate — currently any authenticated
principal (not just order-service) can call them at the service level. The
gateway-level block above is a **mitigation**, not a fix: it closes the
"reachable from the public internet" exposure, but the routes remain
reachable by any authenticated caller *inside* the Docker network (e.g.
another compromised service, or a developer hitting `:8005` directly in
local dev) until `require_scope("inventory:checkout")` is added
service-side. Don't treat the gateway block as sufficient on its own — file
the service-side fix separately.

## cart-service (`:8006`, prefix `/api/v1`)

| Method | Path | Status | Notes |
|---|---|---|---|
| POST | `/guest-carts` | PUBLIC | corrected — this is `/guest-carts`, not `/cart/guest` as an earlier draft of this doc had it |
| GET/POST/PATCH/DELETE | `/cart*` (items, saved-for-later, readiness, merge, clear) | PUBLIC | |
| POST | `/internal/carts/{cart_id}/checked-out` | **BLOCKED** | scope `cart:checkout` |
| POST | `/internal/carts/expire` | **BLOCKED** | scope `cart:expire` |

## order-service (`:8007`, prefix `/api/v1`)

| Method | Path | Status |
|---|---|---|
| POST | `/orders` | PUBLIC |
| GET | `/orders`, `/orders/{id}` | PUBLIC |
| POST | `/orders/{id}/cancel` | PUBLIC |
| POST | `/internal/orders/{id}/payment-authorized` | **BLOCKED** (scope `orders:payment`) |
| POST | `/internal/orders/{id}/payment-failed` | **BLOCKED** (scope `orders:payment`) |
| POST | `/internal/orders/{id}/payment-refunded` | **BLOCKED** (scope `orders:payment`) |
| POST | `/internal/orders/{id}/fulfillment` | **BLOCKED** (scope `orders:fulfillment`) |

## payment-service (`:8008`, prefix `/api/v1`)

| Method | Path | Status | Notes |
|---|---|---|---|
| POST | `/payments` | PUBLIC | buyer/admin |
| GET | `/payments/{id}` | PUBLIC | |
| POST | `/payments/{id}/refund` | PUBLIC | same `require_roles("buyer", "admin")` dependency as the other two routes — ownership presumably enforced in the service layer, not the route |
| POST | `/webhooks/stripe` | **PUBLIC — special case** | no JWT; must bypass gateway auth middleware entirely, body must pass through unmodified for Stripe signature verification |

## shipping-service (`:8009`, prefix `/api/v1`)

| Method | Path | Status |
|---|---|---|
| POST | `/shipments` | PUBLIC (seller/admin enforced downstream) |
| GET | `/shipments/by-order/{order_id}`, `/shipments/{id}` | PUBLIC |
| POST | `/shipments/{id}/ship`, `/{id}/deliver`, `/{id}/exception` | PUBLIC |

No internal-only routes exposed by this service — it only ever calls
*out* to order-service's internal fulfillment callback, it doesn't receive
internal calls itself.

## notification-service (`:8002`)

Every route in this service is gated by the static `X-Internal-API-Key`
header, not a user JWT — it has no end-user-facing routes at all (it's
Celery-backed transactional email, triggered by other services). **Do not
register this service in the gateway's routing table at all.** If a health
dashboard or admin tool ever needs to hit it, that should go over the
Docker network directly, not through the public gateway.

## Services not yet implemented

`audit-service` and `search-service` exist as empty scaffolds under
`services/` with no routes yet — nothing to allowlist until they have
code. Revisit this document when either gets its first route.

