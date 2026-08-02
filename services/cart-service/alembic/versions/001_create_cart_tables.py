"""create cart service tables

Revision ID: 001
Revises:
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "carts",
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("guest_token_hash", sa.String(64), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "CHECKED_OUT",
                "ABANDONED",
                "EXPIRED",
                "MERGED",
                name="cart_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("merged_into_cart_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_carts"),
    )
    op.create_index("ix_carts_expiry", "carts", ["status", "expires_at"])
    op.create_index("ix_carts_guest_token", "carts", ["guest_token_hash"], unique=True)
    op.create_index(
        "uq_active_cart_customer",
        "carts",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE' AND customer_id IS NOT NULL"),
    )
    op.create_table(
        "cart_items",
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("product_name", sa.String(240), nullable=False),
        sa.Column("variant_name", sa.String(200), nullable=False),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("product_version", sa.Integer(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
        sa.CheckConstraint(
            "unit_price >= 0", name="ck_cart_items_unit_price_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"],
            ["carts.id"],
            name="fk_cart_items_cart_id_carts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cart_items"),
        sa.UniqueConstraint("cart_id", "variant_id", name="uq_cart_items_variant"),
    )
    op.create_index("ix_cart_items_cart", "cart_items", ["cart_id", "created_at"])
    op.create_table(
        "saved_items",
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("product_name", sa.String(240), nullable=False),
        sa.Column("variant_name", sa.String(200), nullable=False),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"],
            ["carts.id"],
            name="fk_saved_items_cart_id_carts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_saved_items"),
        sa.UniqueConstraint("cart_id", "variant_id", name="uq_saved_items_variant"),
    )
    op.create_index("ix_saved_items_cart", "saved_items", ["cart_id", "created_at"])
    op.create_table(
        "audit_logs",
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before_data", postgresql.JSONB(), nullable=True),
        sa.Column("after_data", postgresql.JSONB(), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_resource", "audit_logs", ["resource_type", "resource_id"])
    op.create_table(
        "outbox_events",
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
    )
    op.create_index(
        "ix_outbox_pending", "outbox_events", ["published_at", "created_at"]
    )
    op.create_table(
        "idempotency_records",
        sa.Column("actor_key", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),
    )
    op.create_index(
        "uq_idempotency_actor_key",
        "idempotency_records",
        ["actor_key", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("outbox_events")
    op.drop_table("audit_logs")
    op.drop_table("saved_items")
    op.drop_table("cart_items")
    op.drop_table("carts")
