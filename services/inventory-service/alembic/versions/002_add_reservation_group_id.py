"""Add reservation_group_id to inventory_reservations.

Revision ID: 002
Revises: 001
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "inventory_reservations",
        sa.Column("reservation_group_id", uuid_type, nullable=True),
    )
    op.create_index(
        "ix_reservations_group",
        "inventory_reservations",
        ["reservation_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reservations_group", table_name="inventory_reservations")
    op.drop_column("inventory_reservations", "reservation_group_id")
