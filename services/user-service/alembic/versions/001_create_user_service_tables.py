"""Create User Service tables.

Revision ID: 001
Revises:
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


profile_status = sa.Enum(
    "active",
    "deactivated",
    "deletion_pending",
    "deleted",
    name="profile_status",
    native_enum=False,
    create_constraint=True,
)

seller_status = sa.Enum(
    "draft",
    "pending_review",
    "active",
    "suspended",
    "closed",
    name="seller_status",
    native_enum=False,
    create_constraint=True,
)

address_type = sa.Enum(
    "shipping",
    "billing",
    name="address_type",
    native_enum=False,
    create_constraint=True,
)

notification_channel = sa.Enum(
    "email",
    "sms",
    "push",
    "in_app",
    name="notification_channel",
    native_enum=False,
    create_constraint=True,
)

notification_category = sa.Enum(
    "transactional",
    "security",
    "marketing",
    "product_updates",
    name="notification_category",
    native_enum=False,
    create_constraint=True,
)

consent_type = sa.Enum(
    "terms_of_service",
    "privacy_policy",
    "marketing",
    "seller_agreement",
    name="consent_type",
    native_enum=False,
    create_constraint=True,
)

consent_source = sa.Enum(
    "web",
    "mobile",
    "admin",
    "system",
    name="consent_source",
    native_enum=False,
    create_constraint=True,
)

privacy_request_type = sa.Enum(
    "access",
    "export",
    "correction",
    "deletion",
    "restrict_processing",
    name="privacy_request_type",
    native_enum=False,
    create_constraint=True,
)

privacy_request_status = sa.Enum(
    "pending",
    "in_progress",
    "completed",
    "rejected",
    "cancelled",
    name="privacy_request_status",
    native_enum=False,
    create_constraint=True,
)

audit_actor_type = sa.Enum(
    "user",
    "admin",
    "service",
    "system",
    name="audit_actor_type",
    native_enum=False,
    create_constraint=True,
)

audit_action = sa.Enum(
    "created",
    "updated",
    "deleted",
    "deactivated",
    "reactivated",
    "status_changed",
    "default_changed",
    "consent_changed",
    "privacy_requested",
    "privacy_request_resolved",
    "access_granted",
    "access_denied",
    name="audit_action",
    native_enum=False,
    create_constraint=True,
)

audit_outcome = sa.Enum(
    "success",
    "failure",
    "denied",
    name="audit_outcome",
    native_enum=False,
    create_constraint=True,
)


def standard_columns() -> list[sa.Column]:
    """Return columns shared by mutable User Service entities."""
    return [
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "buyer_profiles",
        *standard_columns(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Immutable Identity Service JWT subject",
        ),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column(
            "profile_image_reference",
            sa.String(length=512),
            nullable=True,
            comment="Reference to an externally stored profile image",
        ),
        sa.Column(
            "status",
            profile_status,
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "is_profile_complete",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(trim(display_name)) >= 2",
            name="display_name_min_length",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_buyer_profiles_user_id",
        "buyer_profiles",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "ix_buyer_profiles_status",
        "buyer_profiles",
        ["status"],
        unique=False,
    )

    op.create_table(
        "seller_profiles",
        *standard_columns(),
        sa.Column(
            "buyer_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("business_name", sa.String(length=200), nullable=False),
        sa.Column("store_slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("support_email", sa.String(length=320), nullable=True),
        sa.Column("support_phone", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            seller_status,
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "char_length(trim(business_name)) >= 2",
            name="business_name_min_length",
        ),
        sa.CheckConstraint(
            "char_length(trim(store_slug)) >= 3",
            name="store_slug_min_length",
        ),
        sa.ForeignKeyConstraint(
            ["buyer_profile_id"],
            ["buyer_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_seller_profiles_buyer_profile_id",
        "seller_profiles",
        ["buyer_profile_id"],
        unique=True,
    )
    op.create_index(
        "ix_seller_profiles_store_slug",
        "seller_profiles",
        ["store_slug"],
        unique=True,
    )
    op.create_index(
        "ix_seller_profiles_status",
        "seller_profiles",
        ["status"],
        unique=False,
    )

    op.create_table(
        "addresses",
        *standard_columns(),
        sa.Column(
            "buyer_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("address_type", address_type, nullable=False),
        sa.Column(
            "label",
            sa.String(length=50),
            nullable=True,
            comment="User-defined label such as Home, Office, or Warehouse",
        ),
        sa.Column("recipient_name", sa.String(length=200), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("address_line1", sa.String(length=200), nullable=False),
        sa.Column("address_line2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state_or_region", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=False),
        sa.Column(
            "country_code",
            sa.String(length=2),
            nullable=False,
            comment="Uppercase ISO 3166-1 alpha-2 country code",
        ),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("delivery_instructions", sa.Text(), nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Soft-deletion timestamp",
        ),
        sa.CheckConstraint(
            "char_length(trim(recipient_name)) >= 2",
            name="recipient_name_min_length",
        ),
        sa.CheckConstraint(
            "char_length(trim(address_line1)) >= 3",
            name="address_line1_min_length",
        ),
        sa.CheckConstraint(
            "char_length(trim(city)) >= 2",
            name="city_min_length",
        ),
        sa.CheckConstraint(
            "char_length(trim(postal_code)) >= 3",
            name="postal_code_min_length",
        ),
        sa.CheckConstraint(
            "char_length(country_code) = 2",
            name="country_code_length",
        ),
        sa.CheckConstraint(
            "country_code = upper(country_code)",
            name="country_code_uppercase",
        ),
        sa.ForeignKeyConstraint(
            ["buyer_profile_id"],
            ["buyer_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_addresses_buyer_profile_id",
        "addresses",
        ["buyer_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_addresses_deleted_at",
        "addresses",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_addresses_profile_type",
        "addresses",
        ["buyer_profile_id", "address_type"],
        unique=False,
    )
    op.create_index(
        "ix_addresses_active",
        "addresses",
        ["buyer_profile_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_addresses_default_per_profile_type",
        "addresses",
        ["buyer_profile_id", "address_type"],
        unique=True,
        postgresql_where=sa.text(
            "is_default = true AND deleted_at IS NULL"
        ),
    )

    op.create_table(
        "user_preferences",
        *standard_columns(),
        sa.Column(
            "buyer_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "language_code",
            sa.String(length=35),
            server_default=sa.text("'en-US'"),
            nullable=False,
            comment="BCP 47 language tag",
        ),
        sa.Column(
            "time_zone",
            sa.String(length=64),
            server_default=sa.text("'UTC'"),
            nullable=False,
            comment="IANA time-zone name such as America/New_York",
        ),
        sa.Column(
            "currency_code",
            sa.String(length=3),
            server_default=sa.text("'USD'"),
            nullable=False,
            comment="ISO 4217 currency code",
        ),
        sa.Column(
            "marketplace_code",
            sa.String(length=2),
            server_default=sa.text("'US'"),
            nullable=False,
            comment="Marketplace country using ISO 3166-1 alpha-2",
        ),
        sa.CheckConstraint(
            "char_length(trim(language_code)) >= 2",
            name="language_code_min_length",
        ),
        sa.CheckConstraint(
            "char_length(trim(time_zone)) >= 3",
            name="time_zone_min_length",
        ),
        sa.CheckConstraint(
            "char_length(currency_code) = 3",
            name="currency_code_length",
        ),
        sa.CheckConstraint(
            "currency_code = upper(currency_code)",
            name="currency_code_uppercase",
        ),
        sa.CheckConstraint(
            "char_length(marketplace_code) = 2",
            name="marketplace_code_length",
        ),
        sa.CheckConstraint(
            "marketplace_code = upper(marketplace_code)",
            name="marketplace_code_uppercase",
        ),
        sa.ForeignKeyConstraint(
            ["buyer_profile_id"],
            ["buyer_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_user_preferences_buyer_profile_id",
        "user_preferences",
        ["buyer_profile_id"],
        unique=True,
    )

    op.create_table(
        "notification_preferences",
        *standard_columns(),
        sa.Column(
            "buyer_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("channel", notification_channel, nullable=False),
        sa.Column("category", notification_category, nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["buyer_profile_id"],
            ["buyer_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "buyer_profile_id",
            "channel",
            "category",
            name="buyer_channel_category",
        ),
    )

    op.create_index(
        "ix_notification_preferences_buyer_profile_id",
        "notification_preferences",
        ["buyer_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_preferences_profile_channel",
        "notification_preferences",
        ["buyer_profile_id", "channel"],
        unique=False,
    )
    op.create_index(
        "ix_notification_preferences_profile_category",
        "notification_preferences",
        ["buyer_profile_id", "category"],
        unique=False,
    )

    op.create_table(
        "user_consents",
        *standard_columns(),
        sa.Column(
            "buyer_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("consent_type", consent_type, nullable=False),
        sa.Column(
            "is_granted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "policy_version",
            sa.String(length=50),
            nullable=False,
            comment="Version of the policy presented to the user",
        ),
        sa.Column(
            "source",
            consent_source,
            server_default=sa.text("'web'"),
            nullable=False,
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "policy_reference",
            sa.String(length=512),
            nullable=True,
            comment="Reference to the exact policy document presented",
        ),
        sa.CheckConstraint(
            "char_length(trim(policy_version)) >= 1",
            name="policy_version_not_empty",
        ),
        sa.ForeignKeyConstraint(
            ["buyer_profile_id"],
            ["buyer_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "buyer_profile_id",
            "consent_type",
            name="buyer_consent_type",
        ),
    )

    op.create_index(
        "ix_user_consents_buyer_profile_id",
        "user_consents",
        ["buyer_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_consents_profile_granted",
        "user_consents",
        ["buyer_profile_id", "is_granted"],
        unique=False,
    )

    op.create_table(
        "privacy_requests",
        *standard_columns(),
        sa.Column(
            "buyer_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("request_type", privacy_request_type, nullable=False),
        sa.Column(
            "status",
            privacy_request_status,
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "request_details",
            sa.Text(),
            nullable=True,
            comment="User-provided explanation or correction details",
        ),
        sa.Column(
            "due_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Compliance deadline calculated by the service layer",
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column(
            "result_reference",
            sa.String(length=512),
            nullable=True,
            comment="Short-lived external reference for an export artifact",
        ),
        sa.Column(
            "result_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            """
            (
                status IN ('completed', 'rejected', 'cancelled')
                AND resolved_at IS NOT NULL
            )
            OR
            (
                status IN ('pending', 'in_progress')
                AND resolved_at IS NULL
            )
            """,
            name="resolution_timestamp_matches_status",
        ),
        sa.ForeignKeyConstraint(
            ["buyer_profile_id"],
            ["buyer_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_privacy_requests_buyer_profile_id",
        "privacy_requests",
        ["buyer_profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_privacy_requests_profile_status",
        "privacy_requests",
        ["buyer_profile_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_privacy_requests_status_due",
        "privacy_requests",
        ["status", "due_at"],
        unique=False,
    )
    op.create_index(
        "uq_privacy_requests_active_profile_type",
        "privacy_requests",
        ["buyer_profile_id", "request_type"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'in_progress')"
        ),
    )

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("actor_type", audit_actor_type, nullable=False),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Identity Service subject for a user or administrator actor",
        ),
        sa.Column(
            "actor_reference",
            sa.String(length=200),
            nullable=True,
            comment="Service name or non-user actor identifier",
        ),
        sa.Column(
            "subject_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Identity Service subject affected by the event",
        ),
        sa.Column("action", audit_action, nullable=False),
        sa.Column(
            "outcome",
            audit_outcome,
            server_default=sa.text("'success'"),
            nullable=False,
        ),
        sa.Column(
            "entity_type",
            sa.String(length=100),
            nullable=False,
            comment="Logical entity name such as buyer_profile or address",
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Identifier of the affected entity",
        ),
        sa.Column(
            "before_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Sanitized state before the change",
        ),
        sa.Column(
            "after_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Sanitized state after the change",
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column(
            "source_ip",
            sa.String(length=45),
            nullable=True,
            comment="IPv4 or IPv6 address when collection is permitted",
        ),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="Additional sanitized, non-secret event context",
        ),
        sa.CheckConstraint(
            "char_length(trim(entity_type)) >= 2",
            name="entity_type_min_length",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_audit_logs_entity_timeline",
        "audit_logs",
        ["entity_type", "entity_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_subject_timeline",
        "audit_logs",
        ["subject_user_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_actor_timeline",
        "audit_logs",
        ["actor_type", "actor_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_action_timeline",
        "audit_logs",
        ["action", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_correlation_id",
        "audit_logs",
        ["correlation_id"],
        unique=False,
    )

    # Enforce append-only audit records for direct SQL and bulk operations.
    op.execute(
        """
        CREATE FUNCTION prevent_audit_log_modification()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs is append-only; updates and deletes are prohibited';
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_log_modification();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_audit_logs_append_only
        ON audit_logs;
        """
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prevent_audit_log_modification();"
    )

    op.drop_table("audit_logs")
    op.drop_table("privacy_requests")
    op.drop_table("user_consents")
    op.drop_table("notification_preferences")
    op.drop_table("user_preferences")
    op.drop_table("addresses")
    op.drop_table("seller_profiles")
    op.drop_table("buyer_profiles")