from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDTimestampVersionMixin


class ProfileStatus(StrEnum):
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    DELETION_PENDING = "deletion_pending"


class SellerStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class BuyerProfile(UUIDTimestampVersionMixin, Base):
    __tablename__ = "buyer_profiles"

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    phone_number: Mapped[str | None] = mapped_column(String(32))
    profile_image_reference: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[ProfileStatus] = mapped_column(
        Enum(
            ProfileStatus,
            name="profile_status",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        default=ProfileStatus.ACTIVE,
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_profile_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    seller_profile: Mapped["SellerProfile | None"] = relationship(
        back_populates="buyer_profile", cascade="all, delete-orphan", uselist=False
    )


class SellerProfile(UUIDTimestampVersionMixin, Base):
    __tablename__ = "seller_profiles"

    buyer_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("buyer_profiles.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    business_name: Mapped[str] = mapped_column(String(200))
    store_slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    support_email: Mapped[str | None] = mapped_column(String(320))
    support_phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[SellerStatus] = mapped_column(
        Enum(
            SellerStatus,
            name="seller_status",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        default=SellerStatus.PENDING_REVIEW,
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    buyer_profile: Mapped[BuyerProfile] = relationship(back_populates="seller_profile")
