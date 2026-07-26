from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


JSON_PAYLOAD_TYPE = JSON().with_variant(JSONB, "postgresql")


# ==========================================================
# Enumerations
# ==========================================================

class NotificationType(str, enum.Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"
    SLACK = "SLACK"
    TEAMS = "TEAMS"


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class NotificationPriority(str, enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ProviderType(str, enum.Enum):
    CONSOLE = "CONSOLE"
    SMTP = "SMTP"
    SENDGRID = "SENDGRID"
    SES = "SES"
    MAILGUN = "MAILGUN"


# ==========================================================
# Notification
# ==========================================================

class Notification(Base):
    """
    Represents a notification request.

    One notification may have multiple delivery attempts.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType),
        nullable=False,
    )

    priority: Mapped[NotificationPriority] = mapped_column(
        Enum(NotificationPriority),
        default=NotificationPriority.NORMAL,
        nullable=False,
    )

    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus),
        default=NotificationStatus.PENDING,
        nullable=False,
    )

    provider: Mapped[ProviderType] = mapped_column(
        Enum(ProviderType),
        nullable=False,
    )

    template_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    subject: Mapped[str] = mapped_column(
        String(300),
    )

    recipient: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )

    sender: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    body_html: Mapped[str | None] = mapped_column(
        Text,
    )

    body_text: Mapped[str | None] = mapped_column(
        Text,
    )

    template_data: Mapped[dict | None] = mapped_column(
        JSON_PAYLOAD_TYPE,
        nullable=True,
    )

    external_reference: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
    )

    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    max_retry_count: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False, 
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    attempts: Mapped[list["NotificationAttempt"]] = relationship(
        back_populates="notification",
        cascade="all, delete-orphan",
        order_by="NotificationAttempt.attempt_number",
    )

    def __init__(self, **kwargs: object) -> None:
        if kwargs.get("template_name") is None:
            kwargs["template_name"] = "direct"

        recipient_name = kwargs.pop("recipient_name", None)
        sender_name = kwargs.pop("sender_name", None)
        reply_to_email = kwargs.pop("reply_to_email", None)
        metadata_payload = kwargs.pop("metadata", None)

        super().__init__(**kwargs)

        if recipient_name is not None:
            self.recipient_name = str(recipient_name)

        if sender_name is not None:
            self.sender_name = str(sender_name)

        if reply_to_email is not None:
            self.reply_to_email = str(reply_to_email)

        if metadata_payload is not None:
            payload_dict = (
                dict(metadata_payload)
                if isinstance(metadata_payload, dict)
                else {"value": metadata_payload}
            )
            self._set_internal_value("_metadata", payload_dict)

    @property
    def recipient_name(self) -> str | None:
        return self._get_internal_str("_recipient_name")

    @recipient_name.setter
    def recipient_name(self, value: str | None) -> None:
        self._set_internal_value("_recipient_name", value)

    @property
    def sender_name(self) -> str | None:
        return self._get_internal_str("_sender_name")

    @sender_name.setter
    def sender_name(self, value: str | None) -> None:
        self._set_internal_value("_sender_name", value)

    @property
    def reply_to_email(self) -> str | None:
        return self._get_internal_str("_reply_to_email")

    @reply_to_email.setter
    def reply_to_email(self, value: str | None) -> None:
        self._set_internal_value("_reply_to_email", value)

    def _get_internal_dict(self) -> dict:
        if not isinstance(self.template_data, dict):
            self.template_data = {}

        return self.template_data

    def _get_internal_str(self, key: str) -> str | None:
        value = self._get_internal_dict().get(key)

        return str(value) if value is not None else None

    def _set_internal_value(
        self,
        key: str,
        value: object,
    ) -> None:
        internal = self._get_internal_dict()

        if value is None:
            internal.pop(key, None)
            return

        internal[key] = value


# ==========================================================
# Delivery Attempts
# ==========================================================

class NotificationAttempt(Base):
    """
    Every retry creates a new delivery attempt.
    """

    __tablename__ = "notification_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    provider: Mapped[ProviderType] = mapped_column(
        Enum(ProviderType),
    )

    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus),
    )

    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
    )

    response_code: Mapped[str | None] = mapped_column(
        String(50),
    )

    response_message: Mapped[str | None] = mapped_column(
        Text,
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
    )

    error_stacktrace: Mapped[str | None] = mapped_column(
        Text,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    notification = relationship(
        "Notification",
        back_populates="attempts",
    )

    @property
    def success(self) -> bool:
        return self.status == NotificationStatus.SENT

    @property
    def retryable(self) -> bool:
        return self.status == NotificationStatus.RETRYING

    @property
    def error_message(self) -> str | None:
        if self.success:
            return None

        return self.response_message