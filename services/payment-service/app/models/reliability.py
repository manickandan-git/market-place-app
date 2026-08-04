from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IdempotencyRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        Index(
            "uq_idempotency_actor_key",
            "actor_id",
            "idempotency_key",
            unique=True,
        ),
    )

    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class WebhookEvent(Base, UUIDPrimaryKeyMixin):
    """Dedupe table for at-least-once provider webhook delivery."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "provider_event_id",
            name="uq_webhook_events_provider_event_id",
        ),
    )

    provider: Mapped[str] = mapped_column(String(20), default="stripe", nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
