"""Create payment service tables.

Revision ID: 001
Revises:
Create Date: 2026-08-03
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
        "payments",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("order_id", uuid_type, nullable=False),
        sa.Column("customer_id", uuid_type, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("provider", sa.String(20), server_default="stripe", nullable=False),
        sa.Column("provider_payment_intent_id", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "requires_action",
                "succeeded",
                "failed",
                "refunded",
                "partially_refunded",
                name="payment_status",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("failure_reason", sa.Text()),
        *timestamps(),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("order_id", name="uq_payments_order_id"),
        sa.UniqueConstraint(
            "provider_payment_intent_id",
            name="uq_payments_provider_payment_intent_id",
        ),
    )
    op.create_index("ix_payments_customer", "payments", ["customer_id"])

    op.create_table(
        "refunds",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("payment_id", uuid_type, nullable=False),
        sa.Column("provider_refund_id", sa.String(255)),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.String(120)),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "succeeded",
                "failed",
                name="refund_status",
                native_enum=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        *timestamps(),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_refunds_refund_amount_positive"),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name="fk_refunds_payment_id_payments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refunds"),
    )
    op.create_index("ix_refunds_payment", "refunds", ["payment_id"])

    op.create_table(
        "webhook_events",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("provider", sa.String(20), server_default="stripe", nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_events"),
        sa.UniqueConstraint(
            "provider_event_id",
            name="uq_webhook_events_provider_event_id",
        ),
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
    op.drop_table("webhook_events")
    op.drop_table("refunds")
    op.drop_table("payments")
