"""Create Order Service tables."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "001_create_order_tables"
down_revision = None
branch_labels = None
depends_on = None

order_status = sa.Enum(
    "PENDING_PAYMENT",
    "PAYMENT_AUTHORIZED",
    "CONFIRMED",
    "PROCESSING",
    "SHIPPED",
    "DELIVERED",
    "CANCELLED",
    "PAYMENT_FAILED",
    name="order_status",
)
payment_status = sa.Enum(
    "PENDING", "AUTHORIZED", "CAPTURED", "FAILED", "REFUNDED", name="payment_status"
)


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_number", sa.String(40), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("payment_status", payment_status, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("shipping_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("discount_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("grand_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("shipping_address", postgresql.JSONB(), nullable=False),
        sa.Column("billing_address", postgresql.JSONB(), nullable=False),
        sa.Column("reservation_group_id", postgresql.UUID(as_uuid=True)),
        sa.Column("payment_reference", sa.String(160)),
        sa.Column("cancellation_reason", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("order_number"),
        sa.UniqueConstraint("customer_id", "cart_id", name="uq_order_customer_cart"),
    )
    op.create_index("ix_orders_order_number", "orders", ["order_number"], unique=True)
    op.create_index(
        "ix_orders_customer_created", "orders", ["customer_id", "created_at"]
    )
    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("product_name", sa.String(300), nullable=False),
        sa.Column("variant_name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("product_version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_seller_id", "order_items", ["seller_id"])
    op.create_table(
        "order_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(40)),
        sa.Column("to_status", sa.String(40), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_order_status_history_order_id", "order_status_history", ["order_id"]
    )
    op.create_table(
        "order_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint("actor_id", "key", name="uq_order_idempotency_actor_key"),
    )
    for table in ("order_outbox_events", "order_audit_records"):
        columns = [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "created_at" if table == "order_audit_records" else "occurred_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        ]
        if table == "order_outbox_events":
            columns += [
                sa.Column("aggregate_type", sa.String(60), nullable=False),
                sa.Column(
                    "aggregate_id", postgresql.UUID(as_uuid=True), nullable=False
                ),
                sa.Column("event_type", sa.String(120), nullable=False),
                sa.Column("payload", postgresql.JSONB(), nullable=False),
                sa.Column("correlation_id", sa.String(100)),
                sa.Column("published_at", sa.DateTime(timezone=True)),
            ]
        else:
            columns += [
                sa.Column("actor_id", sa.String(100), nullable=False),
                sa.Column("action", sa.String(120), nullable=False),
                sa.Column("order_id", postgresql.UUID(as_uuid=True)),
                sa.Column("details", postgresql.JSONB(), nullable=False),
                sa.Column("correlation_id", sa.String(100)),
            ]
        op.create_table(table, *columns)


def downgrade() -> None:
    for table in (
        "order_audit_records",
        "order_outbox_events",
        "order_idempotency",
        "order_status_history",
        "order_items",
        "orders",
    ):
        op.drop_table(table)
    payment_status.drop(op.get_bind(), checkfirst=True)
    order_status.drop(op.get_bind(), checkfirst=True)
