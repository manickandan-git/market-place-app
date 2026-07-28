# Product Service architecture

## Ownership

Product Service is the authoritative source for catalog definitions:
categories, products, publication status, variants/SKUs, prices, attributes,
and image references.

It does not own identities, seller profiles, inventory quantities, shopping
carts, orders, reviews, search indexes, media bytes, or notifications.

## Main request flow

1. API Gateway forwards a bearer token.
2. Product Service validates it through Identity JWKS.
3. Authorization checks roles and product ownership from JWT `sub`.
4. Service applies domain rules and optimistic concurrency.
5. Catalog data, audit row, and outbox event commit in one transaction.
6. A future publisher sends outbox events to the shared broker.

## Data choice

PostgreSQL is used for this implementation because SKU uniqueness,
category/product references, transactional publication, audit records, and
outbox atomicity benefit from relational constraints. Flexible product
attributes use JSONB. A later search index can build read-optimized documents
from catalog events without making the search engine authoritative.

