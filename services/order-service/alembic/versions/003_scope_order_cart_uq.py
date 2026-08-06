"""Scope uq_order_customer_cart to non-terminal order statuses.

The plain UNIQUE(customer_id, cart_id) constraint blocked reuse of a cart
forever once *any* order existed for it, including a CANCELLED or
PAYMENT_FAILED one -- even though mark_checked_out already retires the
cart and gives the buyer a fresh one on every successful checkout, so in
healthy operation a cart only ever accumulates one order. The failure mode
this actually needs to guard against is a genuine race between two
concurrent checkouts on the same still-active cart, not a customer whose
order didn't go through. Replacing it with a partial unique index -- the
same pattern cart-service's own uq_active_cart_customer already uses
(WHERE status = 'ACTIVE') -- keeps that race protection for orders still
in flight while letting a terminal order's cart_id be reused.
"""

import sqlalchemy as sa

from alembic import op

revision = "003_scope_order_cart_uq"
down_revision = "002_add_partially_refunded"
branch_labels = None
depends_on = None

# Native enum values are stored from the Python Enum member's .name (see
# 001/002), not its .value -- must be uppercase to match how the ORM
# writes 'OrderStatus.CANCELLED' / 'OrderStatus.PAYMENT_FAILED'.
_TERMINAL_STATUSES = "('CANCELLED', 'PAYMENT_FAILED')"


def upgrade() -> None:
    op.drop_constraint("uq_order_customer_cart", "orders", type_="unique")
    op.create_index(
        "uq_order_customer_cart",
        "orders",
        ["customer_id", "cart_id"],
        unique=True,
        postgresql_where=sa.text(f"status NOT IN {_TERMINAL_STATUSES}"),
    )


def downgrade() -> None:
    op.drop_index("uq_order_customer_cart", table_name="orders")
    op.create_unique_constraint(
        "uq_order_customer_cart", "orders", ["customer_id", "cart_id"]
    )
