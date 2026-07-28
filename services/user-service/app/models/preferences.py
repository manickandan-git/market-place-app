from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDTimestampVersionMixin


class NotificationChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class NotificationCategory(StrEnum):
    ACCOUNT = "account"
    ORDERS = "orders"
    PROMOTIONS = "promotions"


class UserPreference(UUIDTimestampVersionMixin, Base):
    __tablename__ = "user_preferences"

    buyer_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("buyer_profiles.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    language_code: Mapped[str] = mapped_column(String(35), default="en-US")
    time_zone: Mapped[str] = mapped_column(String(64), default="UTC")
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    marketplace_code: Mapped[str] = mapped_column(String(2), default="US")


class NotificationPreference(UUIDTimestampVersionMixin, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("buyer_profile_id", "channel", "category", name="buyer_channel_category"),
    )

    buyer_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("buyer_profiles.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(
            NotificationChannel,
            name="notification_channel",
            values_callable=lambda e: [x.value for x in e],
        )
    )
    category: Mapped[NotificationCategory] = mapped_column(
        Enum(
            NotificationCategory,
            name="notification_category",
            values_callable=lambda e: [x.value for x in e],
        )
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
