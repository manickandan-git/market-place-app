"""Create product catalog tables.

Revision ID: 001_product_catalog
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001_product_catalog"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB(astext_type=sa.Text())


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", UUID, nullable=False),
        sa.Column("parent_id", UUID),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(140), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *timestamps(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name="fk_categories_parent_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
    )
    op.create_index(
        "ix_categories_parent_sort",
        "categories",
        ["parent_id", "sort_order"],
    )

    op.create_table(
        "products",
        sa.Column("id", UUID, nullable=False),
        sa.Column("owner_user_id", UUID, nullable=False),
        sa.Column("category_id", UUID, nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("slug", sa.String(260), nullable=False),
        sa.Column("short_description", sa.String(500)),
        sa.Column("description", sa.Text()),
        sa.Column("brand", sa.String(160)),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "ACTIVE",
                "INACTIVE",
                "ARCHIVED",
                name="product_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("attributes", JSON, nullable=False),
        *timestamps(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_products_category_id_categories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("slug", name="uq_products_slug"),
    )
    op.create_index(
        "ix_products_catalog",
        "products",
        ["status", "category_id", "created_at"],
    )
    op.create_index(
        "ix_products_owner_status",
        "products",
        ["owner_user_id", "status"],
    )

    op.create_table(
        "product_variants",
        sa.Column("id", UUID, nullable=False),
        sa.Column("product_id", UUID, nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("compare_at_price", sa.Numeric(12, 2)),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("attributes", JSON, nullable=False),
        sa.Column("barcode", sa.String(80)),
        sa.Column("weight_grams", sa.Integer()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "compare_at_price IS NULL OR compare_at_price >= price_amount",
            name="ck_product_variants_compare_price_valid",
        ),
        sa.CheckConstraint(
            "price_amount >= 0",
            name="ck_product_variants_price_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_variants_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_variants"),
        sa.UniqueConstraint("sku", name="uq_product_variants_sku"),
    )
    op.create_index(
        "ix_product_variants_product_active",
        "product_variants",
        ["product_id", "is_active"],
    )

    op.create_table(
        "product_images",
        sa.Column("id", UUID, nullable=False),
        sa.Column("product_id", UUID, nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("alt_text", sa.String(300)),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_images_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_images"),
        sa.UniqueConstraint(
            "product_id",
            "sort_order",
            name="uq_product_images_product_sort",
        ),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("actor_id", UUID, nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", UUID, nullable=False),
        sa.Column("before_data", JSON),
        sa.Column("after_data", JSON),
        sa.Column("request_id", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
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
        sa.Column("id", UUID, nullable=False),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("payload", JSON, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
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
        sa.Column("id", UUID, nullable=False),
        sa.Column("actor_id", UUID, nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_id", UUID),
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
    op.drop_table("product_images")
    op.drop_table("product_variants")
    op.drop_table("products")
    op.drop_table("categories")

