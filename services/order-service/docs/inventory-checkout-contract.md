# Inventory batch checkout contract

## Why it is required

Cart exposes SKU and quantity. Inventory currently reserves by its private
`inventory_item_id`. Order must not trust a private ID supplied by a client, so
Inventory resolves active rows by `(seller_id, sku)` while holding database locks.

## Reserve

`POST /api/v1/internal/checkout/reservations/batch`

```json
{
  "cart_reference": "cart-uuid",
  "order_reference": "ORD-20260802-ABC123",
  "expires_at": "2026-08-02T22:15:00Z",
  "lines": [
    {"sku": "PHONE-001-BLK", "seller_id": "seller-uuid", "quantity": 2}
  ]
}
```

Response:

```json
{
  "reservation_group_id": "group-uuid",
  "reservation_ids": ["reservation-uuid"],
  "expires_at": "2026-08-02T22:15:00Z"
}
```

Rules:

- Authenticate the buyer or an Order service token delegated for that buyer.
- Lock all selected inventory rows in a deterministic order.
- Validate SKU is active, belongs to seller, and has sufficient aggregate stock.
- Create all reservation rows or none.
- A replayed `Idempotency-Key` returns the original group.
- Never let available quantity become negative.

## Commit and release

Commit permanently reduces on-hand and reserved quantities. Release only reduces
reserved quantities. Both operations are idempotent at group level and must reject
partial group completion.

```text
POST /api/v1/internal/checkout/reservations/{group_id}/commit
POST /api/v1/internal/checkout/reservations/{group_id}/release
```

These three endpoints are the only addition needed to connect the generated Order
Service safely to the existing Inventory Service.

## Known gaps

Verified directly against `services/inventory-service`'s code (not just
this doc) against the contract's full required security/reliability list.
Everything not listed below — atomic batch reservations, oversell
prevention via row locks, idempotent reserve/commit/release, audit
records, transactional outbox events, protection against
committing released/expired reservations, and seller/active-SKU
validation — is implemented as specified.

### 1. Expiry is not automatic

Expired reservations do not automatically return stock to availability.
`InventoryItem.available_quantity` is `on_hand_quantity - reserved_quantity`
with no expiry check, so a reservation past its `expires_at` still counts
against availability until something explicitly resolves it.

Inventory does expose a sweep for this —
`InventoryService.expire_reservations()` behind
`POST /internal/reservations/expire`, scoped `inventory:expire` per
`services/inventory-service/docs/architecture.md` — but nothing calls it:
no client is registered for that scope in auth-service, and no
scheduler/cron invokes the endpoint anywhere in this stack. A reactive
partial mitigation exists (`commit_reservation`/`commit_reservation_group`
check expiry at commit time and resolve to `EXPIRED` instead of
committing stale stock), but that only fires if someone later tries to
commit that specific reservation — an abandoned cart's hold otherwise sits
locked indefinitely. See `CLAUDE.md`'s "Known gaps" section for the fix
this needs (register `inventory:expire`, add a periodic caller).

### 2. `inventory:checkout` scope — RESOLVED (2026-08-12)

This doc's own "Reserve" rules above used to say to "authenticate the
buyer or an Order service token delegated for that buyer," implying some
scoped restriction that was never actually implemented: all three
checkout routes were gated only by
`AuthenticatedPrincipal = Depends(get_current_principal)` — **any** valid
JWT passed (buyer, seller, admin, or any service token), unlike
`sync_catalog_sku` (`inventory:sync`) and `expire_reservations`
(`inventory:expire`), which were properly scope-gated. Practical
consequence: any buyer's ordinary JWT could call
`POST /internal/checkout/reservations/batch` directly, bypassing
Cart/Order's own business rules, and tie up real stock in a reservation
group that never becomes an order.

Fixed by defining an `inventory:checkout` scope, registering it for
order-service's client in auth-service (alongside its existing
`inventory:commit cart:checkout`), and gating `create_reservation_batch`
with `require_scope("inventory:checkout")` (`app/routes/inventory.py`) —
buyers now only ever reserve stock indirectly, through Order Service's
`POST /api/v1/orders`. Commit/release were left as `AuthenticatedPrincipal`
with their existing inline ownership check (`_locked_group`/
`_active_reservation_with_item`: admin, seller role, the reservation's own
customer, or `inventory:commit` scope) — that was already adequate, per
this doc's original assessment.

**The fix as first written above was incomplete** — it didn't anticipate
that switching order-service from forwarding the buyer's JWT to using its
own service token relocates the buyer's identity out of `principal.subject`
for this call. Two things depended on that identity and both broke,
caught by live verification rather than by the unit tests (which construct
`Principal`/request objects directly and don't exercise this seam):

- **Reservation ownership.** `create_batch_reservation` used to set
  `InventoryReservation.customer_id = principal.subject`. With
  order-service's fixed service subject as the caller, every reservation
  would have been "owned" by order-service itself, not the buyer —
  breaking `_locked_group`'s ownership check the moment the buyer tried to
  release/cancel their own still-pending order (a live `403` on
  `POST /internal/checkout/reservations/{group_id}/release` surfaced this
  immediately). Fixed by adding `customer_id: UUID` to
  `BatchReservationCreate` (required — only scoped callers reach this
  route now, and they always know the buyer) and using `data.customer_id`
  for the reservation rows instead of `principal.subject`. Inventory has
  no pre-existing row to verify this against on a *create* (unlike
  cart-service's `MarkCheckedOutRequest.customer_id`, checked against the
  cart's own owner column) — `inventory:checkout` scope is the entire
  trust boundary for this field, taken on faith.
- **Idempotency scoping.** `IdempotencyRecord.actor_id` was also keyed on
  `principal.subject`, which was safely per-buyer when the buyer's JWT was
  forwarded. With one shared service identity making every checkout call,
  the idempotency namespace collapsed to a single global key space keyed
  on a buyer-controlled `Idempotency-Key` header (8–200 chars, straight
  from `POST /api/v1/orders`) — two different buyers reusing the same
  key value could have collided, either as a spurious `409` blocking a
  legitimate checkout, or, if the request hash happened to match, one
  buyer receiving another buyer's reservation group. Fixed by scoping
  `_idempotency_lookup` (and the `IdempotencyRecord` it writes) to
  `data.customer_id` for this call site specifically, leaving the other
  three callers (seller/admin-authored: `create_inventory_item`,
  `adjust_stock`, single-reservation `create_reservation`) on
  `principal.subject` as before.

order-service's side: `BatchReservationRequest` gained the same
`customer_id: UUID` field, populated from `principal.subject` (the
authenticated buyer making the checkout request, already asserted equal
to `cart.customer_id` earlier in `OrderService.create()`) — not
`cart.customer_id` itself, since `principal.subject` is the verified fact
and `cart.customer_id` is a downstream-reported value. `OrderService.create()`
now calls `self.inventory.reserve_batch(..., await self._service_token(access_token), ...)`
instead of forwarding `access_token` directly, matching how commit/release
already obtained order-service's own authority.

### 3. Outbox events carry no correlation ID

`OutboxEvent` in `app/models/reliability.py` has no `request_id`/
`correlation_id` column, and `InventoryService._event()`'s payload dict
doesn't include one either — even though `CorrelationIdMiddleware` already
propagates `X-Request-ID` correctly everywhere else (order-service forwards
it on every call; it's captured on every `AuditLog` row). Order-service's
own `OutboxEvent` model, by contrast, does have and populate a
`correlation_id` column. A downstream consumer of inventory's outbox events
(once one exists — nothing currently drains this table) would have no way
to correlate an event back to the request that caused it. Fix: add a
`correlation_id` column to `OutboxEvent` and thread `request_id` through
`_event()`'s call sites, mirroring order-service.
