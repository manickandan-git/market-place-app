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
