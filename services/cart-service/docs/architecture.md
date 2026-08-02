# Cart Service architecture

## Ownership

Cart Service owns customer shopping intent: active carts, cart items, saved items,
guest tokens, product/price snapshots, cart expiration, audit logs, idempotency
records, and outbox events.

It does not own product definitions, authoritative prices, stock quantities,
reservations, orders, or payments.

## Service boundaries

| Data or operation | Owning service | Cart behavior |
|---|---|---|
| Product/variant lifecycle | Product Service | Reads active product and variant |
| Authoritative price | Product Service | Stores snapshot; refreshes at readiness |
| Stock quantity | Inventory Service | Reads availability only |
| Stock reservation | Inventory Service | Deferred until checkout starts |
| Shopping intent | Cart Service | Owns active/guest cart and items |
| Order lifecycle | Order Service | Will consume checkout-ready cart |

## Main flows

### Add an item

1. Validate the user JWT through Auth Service JWKS, or hash and validate the
   opaque guest cart token.
2. Lock the cart and compare `If-Match-Version`.
3. Fetch the active Product/Variant from Product Service.
4. Store the product, variant, SKU, price, currency, image, and version snapshot.
5. Commit the cart change, audit record, idempotency record, and outbox event in
   one transaction.

Inventory is not reserved during this flow.

### Checkout readiness

1. Refresh every Product/Variant snapshot.
2. Query Inventory availability for each SKU and quantity.
3. Return price-change and insufficient-stock details.
4. Do not create a reservation.

The future Order Service will begin checkout and ask Inventory Service to create
time-limited reservations.

### Guest merge

The guest token is random and only its SHA-256 hash is stored. After login, the
guest cart is merged into the authenticated buyer's active cart. Duplicate SKUs
have their quantities combined within the configured limit. The guest cart is
marked `merged`, and its token hash is removed so it cannot be reused.

## Reliability and security

- RS256 JWT validation using `kid`, JWKS, issuer, audience, expiry, and `nbf`
- Opaque guest tokens; raw tokens are never persisted
- One active cart per authenticated customer
- `If-Match-Version` optimistic concurrency on mutations
- `Idempotency-Key` support on add-item
- Transactional outbox and audit records
- Correlation ID propagation to Product and Inventory
- Service scopes `cart:checkout` and `cart:expire` for internal operations
- Separate PostgreSQL database owned only by Cart Service
