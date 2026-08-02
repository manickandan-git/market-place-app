from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class CartStatus(StrEnum):
    ACTIVE = "active"
    CHECKED_OUT = "checked_out"
    ABANDONED = "abandoned"
    EXPIRED = "expired"
    MERGED = "merged"


class Cart(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "carts"
    __table_args__ = (
        Index(
            "uq_active_cart_customer",
            "customer_id",
            unique=True,
            postgresql_where="status = 'ACTIVE' AND customer_id IS NOT NULL",
        ),
        Index("ix_carts_guest_token", "guest_token_hash", unique=True),
        Index("ix_carts_expiry", "status", "expires_at"),
    )

    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    guest_token_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[CartStatus] = mapped_column(
        Enum(CartStatus, name="cart_status", native_enum=False),
        default=CartStatus.ACTIVE,
        nullable=False,
    )
    currency_code: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    merged_into_cart_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))

    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", lazy="selectin"
    )
    saved_items: Mapped[list[SavedItem]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", lazy="selectin"
    )


class CartItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "variant_id", name="uq_cart_items_variant"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        Index("ix_cart_items_cart", "cart_id", "created_at"),
    )

    cart_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    product_name: Mapped[str] = mapped_column(String(240), nullable=False)
    variant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    product_version: Mapped[int] = mapped_column(Integer, nullable=False)

    cart: Mapped[Cart] = relationship(back_populates="items")


class SavedItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "saved_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "variant_id", name="uq_saved_items_variant"),
        Index("ix_saved_items_cart", "cart_id", "created_at"),
    )

    cart_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    product_name: Mapped[str] = mapped_column(String(240), nullable=False)
    variant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)

    cart: Mapped[Cart] = relationship(back_populates="saved_items")
