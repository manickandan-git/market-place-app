# Marketplace API Gateway

FastAPI-based reverse proxy that fronts the public-facing routes of every
other service. It has no database and no business logic — its job is edge
policy: routing, an explicit allowlist of what's reachable from the public
internet, CORS, correlation-ID propagation, per-request timeouts, a
per-upstream circuit breaker, and a centralized (but intentionally shallow)
authentication check.

## What this is not

- **Not an authorizer.** `TokenVerifier` (`app/services/token_verifier.py`)
  checks a bearer token's signature, expiry, issuer, and audience via JWKS
  *once*, before proxying — but it never checks roles, scopes, or resource
  ownership, and a request with no `Authorization` header at all skips the
  check entirely (many allowlisted routes, like login/register/public
  catalog reads, are intentionally unauthenticated). Every downstream
  service still does its own full JWT verification and
  role/scope/ownership authorization on every request, unchanged — this is
  purely a fail-fast optimization (reject an obviously bad token before
  spending a network hop on it), not a replacement. Only the owning
  service has the resource-ownership data to authorize correctly (see
  `docs/route-allowlist.md`'s parent conversation). `JWT_ISSUER` /
  `JWT_AUDIENCE` / `JWT_JWKS_URL` here must match auth-service's own
  byte-for-byte, same convention as every other verifying service — a
  mismatch is the most common source of 401s in this codebase per the root
  `CLAUDE.md`, and adding a second verifying service is a second place
  that convention can drift.
- **Not a retrying proxy.** A timeout or connection failure returns
  `502`/`504` immediately, once. Several downstream endpoints are
  non-idempotent (`POST /payments`, `POST /orders`) — a blind gateway-level
  retry could double-charge or double-create. See `ProxyService` in
  `app/services/proxy_service.py`.
- **Not a rate limiter yet.** No rate limiting is implemented in this
  scaffold. If added later, it needs shared (Redis-backed) state, not
  in-memory counters — the gateway may run more than one instance (the
  circuit breaker's in-memory state is fine to duplicate per replica since
  it's a local fast-fail optimization, not a shared limit; rate limiting
  is different because the limit itself is meant to be global).

## Resilience: per-upstream circuit breaker

`CircuitBreaker` (`app/services/circuit_breaker.py`) tracks consecutive
connect/timeout failures per service. After
`CIRCUIT_BREAKER_FAILURE_THRESHOLD` (default 5) in a row, that service's
circuit opens: further requests to it fail immediately with `503
circuit_open` — no network attempt, no waiting out the full
`DOWNSTREAM_TIMEOUT_SECONDS` — for `CIRCUIT_BREAKER_COOLDOWN_SECONDS`
(default 30). After that, the next request is let through as a trial; a
success closes the circuit, a failure reopens it with a fresh cooldown.
This only reacts to transport-level failures (timeout, connect error) —
an upstream returning a normal 4xx/5xx HTTP response is not a breaker
failure, since the service is reachable and answering, just rejecting the
request at the application level.

## Routing model: allowlist, not blocklist

`app/services/routing.py` holds a flat table of `(path prefix → upstream
service)` entries. A request is proxied only if its path matches one of
those prefixes (longest-prefix-match); anything else — including every
`/api/v1/internal/...` path and `/api/v1/auth/service-token` — 404s simply
because no rule exists for it. There is no separate "blocked paths" list to
keep in sync; omission *is* the block. This was a deliberate choice over a
blanket "proxy everything under `/api/v1/<service>`" + blocklist design: a
missed blocklist entry fails open (newly internal-only route becomes
public by accident), a missed allowlist entry fails closed (a legitimate
new route 404s until someone adds it, loudly, in local testing).

`docs/route-allowlist.md` is the per-service audit this table was derived
from, including the reasoning for each path that's excluded (scope-gated
internal callback, client-credentials exchange, health probe, etc.) and one
known gap it deliberately mitigates rather than fixes: inventory-service's
`/internal/checkout/reservations/*` batch endpoints are missing their
`inventory:checkout` scope gate service-side (see root `CLAUDE.md`); this
gateway blocks public access to them, but they're still reachable by any
authenticated caller inside the Docker network until that's fixed
service-side.

`POST /api/v1/webhooks/stripe` is allowlisted but carries no JWT at all —
it's called by Stripe directly, authenticated by Stripe's own signature
inside payment-service, not by anything the gateway checks.

`notification-service` has no entries in the table at all and is not
configured with a base-URL setting — every one of its routes requires a
static `X-Internal-API-Key`, not a user JWT, so it has nothing to expose to
end users.

## Run

```powershell
Copy-Item .env.example .env
docker compose up --build -d marketplace-api-gateway
curl http://localhost:9000/health
curl http://localhost:9000/ready
```

Or locally:

```powershell
uv sync
uv run uvicorn app.main:app --reload --port 9000
```

## Health checks

- `GET /health` — gateway liveness only, no downstream calls.
- `GET /ready` — additionally fans out a 2s-timeout `GET /health` to every
  configured upstream and reports per-service reachability; returns `503`
  if any are unreachable. This is the gateway's own internal readiness
  probe for orchestration — it is not a proxied route and never appears in
  `routing.py`'s allowlist.

## Adding a new route

1. Confirm the route in the owning service's `app/routes*.py` — get the
   exact path, including any router-level `prefix=`.
2. Decide PUBLIC or BLOCKED using the rules at the top of
   `docs/route-allowlist.md`, and add a row to that service's table there.
3. Only if PUBLIC: add a `Route(...)` entry to `ALLOWLIST` in
   `app/services/routing.py`, then add or extend a case in
   `tests/test_routing.py` covering it.
