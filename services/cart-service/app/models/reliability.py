from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_resource", "resource_type", "resource_id"),)

    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OutboxEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_pending", "published_at", "created_at"),)

    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        Index("uq_idempotency_actor_key", "actor_key", "idempotency_key", unique=True),
    )

    actor_key: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    response_body: Mapped[str | None] = mapped_column(Text)
