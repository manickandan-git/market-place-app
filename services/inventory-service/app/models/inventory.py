from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"


class MovementType(StrEnum):
    RECEIPT = "receipt"
    ADJUSTMENT = "adjustment"
    RESERVATION = "reservation"
    RELEASE = "release"
    COMMITMENT = "commitment"
    RETURN = "return"


class MovementReason(StrEnum):
    PURCHASE_RECEIPT = "purchase_receipt"
    CYCLE_COUNT = "cycle_count"
    DAMAGE = "damage"
    CUSTOMER_ORDER = "customer_order"
    RESERVATION_EXPIRED = "reservation_expired"
    CUSTOMER_CANCELLED = "customer_cancelled"
    CUSTOMER_RETURN = "customer_return"
    ADMIN_CORRECTION = "admin_correction"


class CatalogSku(Base, TimestampMixin, VersionMixin):
    """Local projection of a Product Service variant; never owns product content."""

    __tablename__ = "catalog_skus"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_catalog_skus_sku"),
        Index("ix_catalog_skus_seller_active", "seller_id", "is_active"),
    )

    variant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    seller_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Warehouse(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("code", name="uq_warehouses_code"),
        Index("ix_warehouses_active_name", "is_active", "name"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address_reference: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    inventory_items: Mapped[list[InventoryItem]] = relationship(
        back_populates="warehouse",
    )


class InventoryItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint(
            "warehouse_id",
            "sku",
            name="uq_inventory_items_warehouse_sku",
        ),
        CheckConstraint("on_hand_quantity >= 0", name="on_hand_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="reserved_non_negative"),
        CheckConstraint(
            "reserved_quantity <= on_hand_quantity",
            name="reserved_not_above_on_hand",
        ),
        CheckConstraint("low_stock_threshold >= 0", name="threshold_non_negative"),
        Index("ix_inventory_items_sku", "sku"),
        Index("ix_inventory_items_seller_sku", "seller_id", "sku"),
    )

    warehouse_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    seller_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    on_hand_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    warehouse: Mapped[Warehouse] = relationship(back_populates="inventory_items")
    reservations: Mapped[list[InventoryReservation]] = relationship(
        back_populates="inventory_item",
    )
    movements: Mapped[list[InventoryMovement]] = relationship(
        back_populates="inventory_item",
    )

    @property
    def available_quantity(self) -> int:
        return self.on_hand_quantity - self.reserved_quantity


class InventoryReservation(
    Base,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    VersionMixin,
):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="reservation_quantity_positive"),
        Index("ix_reservations_status_expiry", "status", "expires_at"),
        Index("ix_reservations_order", "order_reference"),
        Index("ix_reservations_owner", "customer_id", "status"),
        Index("ix_reservations_group", "reservation_group_id"),
    )

    inventory_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    cart_reference: Mapped[str | None] = mapped_column(String(120))
    order_reference: Mapped[str | None] = mapped_column(String(120))
    reservation_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status", native_enum=False),
        default=ReservationStatus.ACTIVE,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    inventory_item: Mapped[InventoryItem] = relationship(
        back_populates="reservations",
    )


class InventoryMovement(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint(
            "on_hand_delta <> 0 OR reserved_delta <> 0",
            name="movement_has_delta",
        ),
        Index("ix_movements_item_created", "inventory_item_id", "created_at"),
        Index("ix_movements_reference", "reference_type", "reference_id"),
    )

    inventory_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    movement_type: Mapped[MovementType] = mapped_column(
        Enum(MovementType, name="movement_type", native_enum=False),
        nullable=False,
    )
    reason: Mapped[MovementReason] = mapped_column(
        Enum(MovementReason, name="movement_reason", native_enum=False),
        nullable=False,
    )
    on_hand_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resulting_on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(60))
    reference_id: Mapped[str | None] = mapped_column(String(120))
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    inventory_item: Mapped[InventoryItem] = relationship(back_populates="movements")
