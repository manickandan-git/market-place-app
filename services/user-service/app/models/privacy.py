from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDTimestampVersionMixin


class PrivacyRequestType(StrEnum):
    ACCESS = "access"
    EXPORT = "export"
    CORRECTION = "correction"
    DELETION = "deletion"


class PrivacyRequestStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PrivacyRequest(UUIDTimestampVersionMixin, Base):
    __tablename__ = "privacy_requests"
    __table_args__ = (
        Index(
            "uq_active_privacy_request_per_type",
            "buyer_profile_id",
            "request_type",
            unique=True,
            postgresql_where=text("status IN ('pending', 'in_progress')"),
        ),
    )

    buyer_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("buyer_profiles.id", ondelete="CASCADE"), index=True
    )
    request_type: Mapped[PrivacyRequestType] = mapped_column(
        Enum(
            PrivacyRequestType,
            name="privacy_request_type",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        )
    )
    status: Mapped[PrivacyRequestStatus] = mapped_column(
        Enum(
            PrivacyRequestStatus,
            name="privacy_request_status",
            native_enum=False,
            values_callable=lambda e: [x.value for x in e],
        ),
        default=PrivacyRequestStatus.PENDING,
    )
    request_details: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    result_reference: Mapped[str | None] = mapped_column(String(512))
    result_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
