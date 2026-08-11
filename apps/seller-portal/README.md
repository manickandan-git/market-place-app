# Seller Portal

Angular app for sellers to manage their own catalog, stock, orders, and
shipments. Buyer-facing storefront (`apps/buyer-portal`, Next.js) is a separate app —
see `apps/buyer-portal/AGENTS.md` for why they aren't merged. This is a planning doc,
written before implementation; sections will be filled in / corrected as
decisions get made.

## Audience & scope

Single-tenant per session: a logged-in seller manages **their own** data
only (never cross-seller). Not an admin console — platform-wide operations
(cross-seller moderation, disputes, etc.) are explicitly out of scope; if
that's ever needed it should be its own app, not a role branch bolted onto
this one (different trust level, higher blast radius if a UI bug leaks data
across sellers).

Phase 1 feature set:

- **Product catalog management** — create/edit products, categories,
  variants/SKUs (`product-service`)
- **Inventory management** — warehouses, stock levels, low-stock visibility
  (`inventory-service`)
- **Order management** — view/manage orders containing this seller's items
  (`order-service`)
- **Shipment tracking** — create shipments, update tracking status
  (`shipping-service`)

## Backend integration

All calls go through `api-gateway` (`:9000`), the same pattern `apps/buyer-portal`
uses — single origin, gateway handles allowlisting/CORS/circuit-breaking;
downstream services still do their own JWT + role/ownership checks
unchanged.

Per `services/api-gateway/docs/route-allowlist.md` (snapshot 2026-08-05,
re-verify against source before relying on it), the seller-relevant routes
are already gateway-PUBLIC with seller/admin + ownership enforced
downstream — no gateway route changes needed for phase 1, only a CORS
origin addition (see below):

| Service | Routes | Notes |
|---|---|---|
| product-service | `/api/v1/seller/products*` | seller/admin + ownership enforced downstream |
| inventory-service | `/api/v1/seller/inventory*` | seller/admin + ownership enforced downstream |
| order-service | `/api/v1/orders`, `/api/v1/orders/{id}` | **does not work for sellers — see blocker below** |
| shipping-service | `/api/v1/shipments*` | seller/admin enforced downstream |

**Gateway change required:** add the seller portal's dev/prod origin to
`cors_origins` in `services/api-gateway/app/config.py` (currently defaults
to `["http://localhost:3000"]`, i.e. just `apps/buyer-portal`).

**Backend blocker — order-service has no seller-facing order endpoint.**
Verified against source (2026-08-11), not just the allowlist doc:

- `GET /orders` (`app/repository.py:42`, `list_for_customer`) filters
  strictly by `Order.customer_id == principal.subject` — a seller calling
  this gets their own (empty) buyer order history, never their sales.
- `GET /orders/{id}` (`app/service.py:226`, `customer_order`) only permits
  the order's own `customer_id` or an `admin` role — a seller is neither,
  so this 403s.
- The data needed already exists per line item — `OrderItem.seller_id` is
  a real, indexed column (`app/models.py:121`) — it's just never queried
  by it anywhere in the service. No route, no repository method.

This is the same gap the root `CLAUDE.md` already documents in the
shipping-service section (Shipping "can't independently verify a seller
actually owns line items on an order" for the identical reason). The
seller portal's order-management feature is blocked on this until
order-service adds something like `GET /seller/orders` (list orders
containing the caller's line items, seller/admin + ownership enforced,
mirroring the `/seller/products*` and `/seller/inventory*` pattern already
used by product-service and inventory-service) plus a repository method to
back it (e.g. a join/filter on `OrderItem.seller_id`). That's a
order-service change, not something this frontend can work around —
flagging here so it's sequenced before the order-management screens, not
discovered while building them.

## Auth

JWTs come from `auth-service` exactly like `apps/buyer-portal` (`POST /auth/login`,
`POST /auth/token`, `POST /auth/refresh`), gated to accounts with the
`seller` role.

**Difference from `apps/buyer-portal` that matters:** `apps/buyer-portal` stores tokens
server-side via httpOnly cookies set through Next.js server
actions/route handlers (`src/lib/session.ts`, `src/proxy.ts`) — there's no
server tier to do that in an Angular SPA. Options to decide between before
building the auth module:

1. In-memory access token (survives only the JS session) + httpOnly refresh
   cookie issued by auth-service, silent-refresh on load — safer against
   XSS token theft, more moving parts.
2. Access + refresh tokens both in browser storage (`localStorage` or
   `sessionStorage`) — simplest to implement, weaker against XSS.

Leaning toward (1) for parity with how `apps/buyer-portal` avoids putting tokens in
JS-reachable storage, but this is a real tradeoff to make deliberately, not
copy blindly — revisit once auth-service's refresh-token/cookie support for
non-Next.js clients is confirmed.

`src/lib/jwt.ts` in `apps/buyer-portal` (decode-without-verify, used only for
proactive-refresh timing) is small and framework-agnostic enough to port
as-is if useful.

## Tech stack

- Angular, latest stable, standalone components (no NgModules), signals for
  state where it fits
- State management: TBD — likely signals + services for phase-1 scope
  (product/inventory/order/shipment CRUD), revisit if complexity grows
- Styling: TBD
- HTTP: Angular `HttpClient` + an `HttpInterceptor` for attaching the bearer
  token and handling 401 → refresh

## Deployment

New sibling app under `apps/`, own `package.json`, own `Dockerfile`, own
port (TBD — `apps/buyer-portal` currently runs on `3001` in Docker / `3000` locally
per recent compose changes, so pick something that doesn't collide), own
entry in the root `docker-compose.yml`.

## Open questions

- Token storage strategy (see Auth section above) — needs a decision before
  the auth module is built, not after.
- Seller registration/onboarding: does this app also handle
  `POST /me/seller` (user-service) for a buyer becoming a seller, or is
  that assumed to happen elsewhere first?
