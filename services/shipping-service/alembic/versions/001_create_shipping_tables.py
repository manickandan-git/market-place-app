"""Create shipping service tables.

Revision ID: 001
Revises:
Create Date: 2026-08-04
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
        "shipments",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("order_id", uuid_type, nullable=False),
        sa.Column("seller_id", uuid_type, nullable=False),
        sa.Column("carrier", sa.String(80), nullable=False),
        sa.Column("service_level", sa.String(80)),
        sa.Column("tracking_number", sa.String(160)),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "shipped",
                "delivered",
                "failed",
                name="shipment_status",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("shipped_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_shipments"),
        sa.UniqueConstraint("order_id", name="uq_shipments_order_id"),
    )
    op.create_index("ix_shipments_seller", "shipments", ["seller_id"])

    op.create_table(
        "shipment_events",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("shipment_id", uuid_type, nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("description", sa.String(280)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_shipment_events"),
        sa.ForeignKeyConstraint(
            ["shipment_id"],
            ["shipments.id"],
            name="fk_shipment_events_shipment_id_shipments",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_shipment_events_shipment", "shipment_events", ["shipment_id"]
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("actor_id", uuid_type, nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(60), nullable=False),
        sa.Column("resource_id", uuid_type),
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
    op.drop_table("shipment_events")
    op.drop_table("shipments")
