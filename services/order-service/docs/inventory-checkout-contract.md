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

### 2. No `inventory:checkout` scope — the checkout endpoints aren't actually Order-Service-only

This doc's own "Reserve" rules above say to "authenticate the buyer or an
Order service token delegated for that buyer," implying some scoped
restriction. That was never implemented. All three checkout routes —
`/internal/checkout/reservations/batch`, `/{group_id}/commit`,
`/{group_id}/release` — are gated only by
`AuthenticatedPrincipal = Depends(get_current_principal)` in
`app/routes/inventory.py`: **any** valid JWT passes (buyer, seller, admin,
or any service token), with no `require_scope` check at all. Compare to
`sync_catalog_sku` (`inventory:sync`) and `expire_reservations`
(`inventory:expire`), which are properly scope-gated.

Practical consequence: any buyer's ordinary JWT can call
`POST /internal/checkout/reservations/batch` directly, bypassing
Cart/Order's own business rules (price snapshot, cart-readiness checks),
and tie up real stock in a reservation group that never becomes an order —
a stock-locking vector with no authorization boundary today. Commit/release
at least have an inline ownership check (`_locked_group`/
`_active_reservation_with_item`: admin, seller role, the reservation's own
customer, or `inventory:commit` scope), but reservation creation has none.

Fix: define an `inventory:checkout` scope, register it for order-service's
client in auth-service (alongside its existing `inventory:commit
cart:checkout`), and gate `create_reservation_batch` with
`require_scope("inventory:checkout")` — buyers would then only ever reserve
stock indirectly, through Order Service's `POST /api/v1/orders`, never by
calling Inventory's internal endpoint directly.

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
