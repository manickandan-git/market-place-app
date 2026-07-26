from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# ============================================================
# Alembic revision identifiers
# ============================================================

revision: str = "001_create_notifications_tables"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# ============================================================
# PostgreSQL enum definitions
# ============================================================

notification_type_enum = postgresql.ENUM(
    "EMAIL",
    "SMS",
    "PUSH",
    "SLACK",
    "TEAMS",
    name="notificationtype",
    create_type=False,
)

notification_status_enum = postgresql.ENUM(
    "PENDING",
    "PROCESSING",
    "SENT",
    "FAILED",
    "RETRYING",
    "CANCELLED",
    name="notificationstatus",
    create_type=False,
)

notification_priority_enum = postgresql.ENUM(
    "LOW",
    "NORMAL",
    "HIGH",
    "CRITICAL",
    name="notificationpriority",
    create_type=False,
)

provider_type_enum = postgresql.ENUM(
    "CONSOLE",
    "SMTP",
    "SENDGRID",
    "SES",
    "MAILGUN",
    name="providertype",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # ========================================================
    # Create enum types
    # ========================================================

    notification_type_enum.create(
        bind,
        checkfirst=True,
    )

    notification_status_enum.create(
        bind,
        checkfirst=True,
    )

    notification_priority_enum.create(
        bind,
        checkfirst=True,
    )

    provider_type_enum.create(
        bind,
        checkfirst=True,
    )

    # ========================================================
    # Create notifications table
    # ========================================================

    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "type",
            notification_type_enum,
            nullable=False,
        ),
        sa.Column(
            "priority",
            notification_priority_enum,
            nullable=False,
            server_default="NORMAL",
        ),
        sa.Column(
            "status",
            notification_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "provider",
            provider_type_enum,
            nullable=False,
        ),
        sa.Column(
            "template_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "subject",
            sa.String(length=300),
            nullable=False,
        ),
        sa.Column(
            "recipient",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "sender",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "body_html",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "body_text",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "template_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "external_reference",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "provider_message_id",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_retry_count",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "retry_count >= 0",
            name="ck_notifications_retry_count_non_negative",
        ),
        sa.CheckConstraint(
            "max_retry_count >= 0",
            name="ck_notifications_max_retry_count_non_negative",
        ),
        sa.CheckConstraint(
            "retry_count <= max_retry_count",
            name="ck_notifications_retry_count_within_limit",
        ),
    )

    # ========================================================
    # Notification indexes
    # ========================================================

    op.create_index(
        "ix_notifications_recipient",
        "notifications",
        ["recipient"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_external_reference",
        "notifications",
        ["external_reference"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_status",
        "notifications",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_type",
        "notifications",
        ["type"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_provider",
        "notifications",
        ["provider"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_priority",
        "notifications",
        ["priority"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_created_at",
        "notifications",
        ["created_at"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_scheduled_at",
        "notifications",
        ["scheduled_at"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_status_scheduled_at",
        "notifications",
        ["status", "scheduled_at"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_recipient_created_at",
        "notifications",
        ["recipient", "created_at"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_external_reference_type",
        "notifications",
        ["external_reference", "type"],
        unique=False,
    )

    # ========================================================
    # Create notification_attempts table
    # ========================================================

    op.create_table(
        "notification_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "provider",
            provider_type_enum,
            nullable=False,
        ),
        sa.Column(
            "status",
            notification_status_enum,
            nullable=False,
        ),
        sa.Column(
            "provider_message_id",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "response_code",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "response_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "error_stacktrace",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name="fk_notification_attempts_notification_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_id",
            "attempt_number",
            name="uq_notification_attempt_number",
        ),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_notification_attempt_number_positive",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_notification_attempt_latency_non_negative",
        ),
    )

    # ========================================================
    # Notification-attempt indexes
    # ========================================================

    op.create_index(
        "ix_notification_attempts_notification_id",
        "notification_attempts",
        ["notification_id"],
        unique=False,
    )

    op.create_index(
        "ix_notification_attempts_status",
        "notification_attempts",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_notification_attempts_provider",
        "notification_attempts",
        ["provider"],
        unique=False,
    )

    op.create_index(
        "ix_notification_attempts_created_at",
        "notification_attempts",
        ["created_at"],
        unique=False,
    )

    op.create_index(
        "ix_notification_attempts_notification_created",
        "notification_attempts",
        ["notification_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    # ========================================================
    # Drop notification_attempts
    # ========================================================

    op.drop_index(
        "ix_notification_attempts_notification_created",
        table_name="notification_attempts",
    )

    op.drop_index(
        "ix_notification_attempts_created_at",
        table_name="notification_attempts",
    )

    op.drop_index(
        "ix_notification_attempts_provider",
        table_name="notification_attempts",
    )

    op.drop_index(
        "ix_notification_attempts_status",
        table_name="notification_attempts",
    )

    op.drop_index(
        "ix_notification_attempts_notification_id",
        table_name="notification_attempts",
    )

    op.drop_table("notification_attempts")

    # ========================================================
    # Drop notifications
    # ========================================================

    op.drop_index(
        "ix_notifications_external_reference_type",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_recipient_created_at",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_status_scheduled_at",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_scheduled_at",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_created_at",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_priority",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_provider",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_type",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_status",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_external_reference",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_recipient",
        table_name="notifications",
    )

    op.drop_table("notifications")

    # ========================================================
    # Drop PostgreSQL enum types
    # ========================================================

    provider_type_enum.drop(
        bind,
        checkfirst=True,
    )

    notification_priority_enum.drop(
        bind,
        checkfirst=True,
    )

    notification_status_enum.drop(
        bind,
        checkfirst=True,
    )

    notification_type_enum.drop(
        bind,
        checkfirst=True,
    )