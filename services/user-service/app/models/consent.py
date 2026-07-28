from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDTimestampVersionMixin


class ConsentType(StrEnum):
    PRIVACY_POLICY = "privacy_policy"
    TERMS_OF_SERVICE = "terms_of_service"
    MARKETING = "marketing"


class ConsentSource(StrEnum):
    WEB = "web"
    MOBILE = "mobile"
    ADMIN = "admin"


class UserConsent(UUIDTimestampVersionMixin, Base):
    __tablename__ = "user_consents"
    __table_args__ = (
        UniqueConstraint("buyer_profile_id", "consent_type", name="buyer_consent_type"),
    )

    buyer_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("buyer_profiles.id", ondelete="CASCADE"), index=True
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        Enum(
            ConsentType,
            name="consent_type",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        )
    )
    is_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_version: Mapped[str] = mapped_column(String(50))
    source: Mapped[ConsentSource] = mapped_column(
        Enum(
            ConsentSource,
            name="consent_source",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        )
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    policy_reference: Mapped[str | None] = mapped_column(String(512))
