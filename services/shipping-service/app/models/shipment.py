from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class ShipmentStatus(StrEnum):
    PENDING = "pending"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    FAILED = "failed"


class Shipment(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    """One shipment per order — matches Order's own whole-order fulfillment
    model (there is no per-line/per-seller fulfillment state to attach
    multiple shipments to). See docs/shipping-service-scope.md."""

    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_shipments_order_id"),
        Index("ix_shipments_seller", "seller_id"),
    )

    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    seller_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    carrier: Mapped[str] = mapped_column(String(80), nullable=False)
    service_level: Mapped[str | None] = mapped_column(String(80))
    tracking_number: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(ShipmentStatus, name="shipment_status", native_enum=False),
        default=ShipmentStatus.PENDING,
        nullable=False,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list[ShipmentEvent]] = relationship(
        back_populates="shipment", lazy="selectin", order_by="ShipmentEvent.occurred_at"
    )


class ShipmentEvent(Base, UUIDPrimaryKeyMixin):
    """Manually-recorded tracking history — there is no real carrier
    integration in this version (see docs/shipping-service-scope.md), so
    these rows are appended by the seller/admin alongside each status
    change rather than polled from a carrier API."""

    __tablename__ = "shipment_events"
    __table_args__ = (Index("ix_shipment_events_shipment", "shipment_id"),)

    shipment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(String(280))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    shipment: Mapped[Shipment] = relationship(back_populates="events")
