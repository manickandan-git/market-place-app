"""Create inventory service tables.

Revision ID: 001
Revises:
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)
json_type = postgresql.JSONB(astext_type=sa.Text())


def timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "catalog_skus",
        sa.Column("variant_id", uuid_type, nullable=False),
        sa.Column("product_id", uuid_type, nullable=False),
        sa.Column("seller_id", uuid_type, nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        *timestamps(),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("variant_id", name="pk_catalog_skus"),
        sa.UniqueConstraint("sku", name="uq_catalog_skus_sku"),
    )
    op.create_index(
        "ix_catalog_skus_seller_active",
        "catalog_skus",
        ["seller_id", "is_active"],
    )

    op.create_table(
        "warehouses",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("address_reference", sa.String(200)),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        *timestamps(),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_warehouses"),
        sa.UniqueConstraint("code", name="uq_warehouses_code"),
    )
    op.create_index(
        "ix_warehouses_active_name",
        "warehouses",
        ["is_active", "name"],
    )

    op.create_table(
        "inventory_items",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("warehouse_id", uuid_type, nullable=False),
        sa.Column("product_id", uuid_type, nullable=False),
        sa.Column("variant_id", uuid_type, nullable=False),
        sa.Column("seller_id", uuid_type, nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column(
            "on_hand_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "reserved_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "low_stock_threshold",
            sa.Integer(),
            server_default="5",
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        *timestamps(),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "on_hand_quantity >= 0",
            name="ck_inventory_items_on_hand_non_negative",
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0",
            name="ck_inventory_items_reserved_non_negative",
        ),
        sa.CheckConstraint(
            "reserved_quantity <= on_hand_quantity",
            name="ck_inventory_items_reserved_not_above_on_hand",
        ),
        sa.CheckConstraint(
            "low_stock_threshold >= 0",
            name="ck_inventory_items_threshold_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_inventory_items_warehouse_id_warehouses",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_items"),
        sa.UniqueConstraint(
            "warehouse_id",
            "sku",
            name="uq_inventory_items_warehouse_sku",
        ),
    )
    op.create_index("ix_inventory_items_sku", "inventory_items", ["sku"])
    op.create_index(
        "ix_inventory_items_seller_sku",
        "inventory_items",
        ["seller_id", "sku"],
    )

    op.create_table(
        "inventory_reservations",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("inventory_item_id", uuid_type, nullable=False),
        sa.Column("customer_id", uuid_type, nullable=False),
        sa.Column("cart_reference", sa.String(120)),
        sa.Column("order_reference", sa.String(120)),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "committed",
                "released",
                "expired",
                name="reservation_status",
                native_enum=False,
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_inventory_reservations_reservation_quantity_positive",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"],
            ["inventory_items.id"],
            name=(
                "fk_inventory_reservations_inventory_item_id_"
                "inventory_items"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_reservations"),
    )
    op.create_index(
        "ix_reservations_status_expiry",
        "inventory_reservations",
        ["status", "expires_at"],
    )
    op.create_index(
        "ix_reservations_order",
        "inventory_reservations",
        ["order_reference"],
    )
    op.create_index(
        "ix_reservations_owner",
        "inventory_reservations",
        ["customer_id", "status"],
    )

    op.create_table(
        "inventory_movements",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("inventory_item_id", uuid_type, nullable=False),
        sa.Column(
            "movement_type",
            sa.Enum(
                "receipt",
                "adjustment",
                "reservation",
                "release",
                "commitment",
                "return",
                name="movement_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "reason",
            sa.Enum(
                "purchase_receipt",
                "cycle_count",
                "damage",
                "customer_order",
                "reservation_expired",
                "customer_cancelled",
                "customer_return",
                "admin_correction",
                name="movement_reason",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("on_hand_delta", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved_delta", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resulting_on_hand", sa.Integer(), nullable=False),
        sa.Column("resulting_reserved", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(60)),
        sa.Column("reference_id", sa.String(120)),
        sa.Column("actor_id", uuid_type, nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "on_hand_delta <> 0 OR reserved_delta <> 0",
            name="ck_inventory_movements_movement_has_delta",
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"],
            ["inventory_items.id"],
            name="fk_inventory_movements_inventory_item_id_inventory_items",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_movements"),
    )
    op.create_index(
        "ix_movements_item_created",
        "inventory_movements",
        ["inventory_item_id", "created_at"],
    )
    op.create_index(
        "ix_movements_reference",
        "inventory_movements",
        ["reference_type", "reference_id"],
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("actor_id", uuid_type, nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", uuid_type, nullable=False),
        sa.Column("before_data", json_type),
        sa.Column("after_data", json_type),
        sa.Column("request_id", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index(
        "ix_audit_resource",
        "audit_logs",
        ["resource_type", "resource_id"],
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", uuid_type, nullable=False),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
    )
    op.create_index(
        "ix_outbox_pending",
        "outbox_events",
        ["published_at", "created_at"],
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("actor_id", uuid_type, nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(60), nullable=False),
        sa.Column("resource_id", uuid_type),
        sa.Column("response_body", sa.Text()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_records"),
    )
    op.create_index(
        "uq_idempotency_actor_key",
        "idempotency_records",
        ["actor_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("idempotency_records")
    op.drop_table("outbox_events")
    op.drop_table("audit_logs")
    op.drop_table("inventory_movements")
    op.drop_table("inventory_reservations")
    op.drop_table("inventory_items")
    op.drop_table("warehouses")
    op.drop_table("catalog_skus")
