"""Add PARTIALLY_REFUNDED to payment_status enum."""

from alembic import op

revision = "002_add_partially_refunded"
down_revision = "001_create_order_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Native enum values are stored from the Python Enum member's .name
    # (see 001), not its .value — must be uppercase to match how the ORM
    # writes 'PaymentStatus.PARTIALLY_REFUNDED'.
    op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'PARTIALLY_REFUNDED'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enum types; removing one requires
    # rebuilding the type and every column/index that uses it. Not worth
    # supporting for a value that's additive and harmless to leave behind.
    raise NotImplementedError("payment_status enum values cannot be removed")
