from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDTimestampVersionMixin


class AddressType(StrEnum):
    SHIPPING = "shipping"
    BILLING = "billing"


class Address(UUIDTimestampVersionMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = (
        Index(
            "uq_active_default_address_per_type",
            "buyer_profile_id",
            "address_type",
            unique=True,
            postgresql_where=text("is_default = true AND deleted_at IS NULL"),
        ),
    )

    buyer_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("buyer_profiles.id", ondelete="CASCADE"), index=True
    )
    address_type: Mapped[AddressType] = mapped_column(
        Enum(AddressType, name="address_type", values_callable=lambda e: [x.value for x in e])
    )
    label: Mapped[str | None] = mapped_column(String(50))
    recipient_name: Mapped[str] = mapped_column(String(200))
    company_name: Mapped[str | None] = mapped_column(String(200))
    address_line1: Mapped[str] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    state_or_region: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str] = mapped_column(String(32))
    country_code: Mapped[str] = mapped_column(String(2))
    phone_number: Mapped[str | None] = mapped_column(String(32))
    delivery_instructions: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
