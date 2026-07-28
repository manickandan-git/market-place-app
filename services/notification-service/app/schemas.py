from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from app.models import (
    NotificationPriority,
    NotificationStatus,
    NotificationType,
    ProviderType,
)

# ============================================================
# Shared schemas
# ============================================================


class MessageResponse(BaseModel):
    """
    Generic API response for operations that return only a message.
    """

    message: str


class PaginationMetadata(BaseModel):
    """
    Pagination information returned with notification lists.
    """

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


# ============================================================
# Recipient and sender schemas
# ============================================================


class EmailRecipient(BaseModel):
    """
    Represents one email recipient.

    The name is optional because the service may receive only an email
    address from another microservice.
    """

    email: EmailStr
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


class EmailSender(BaseModel):
    """
    Optional sender information for a notification.

    When omitted, the Notification Service uses its configured default
    sender name and email address.
    """

    email: str = Field(
        min_length=3,
        max_length=320,
    )
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )


# ============================================================
# Base notification request
# ============================================================


class BaseNotificationRequest(BaseModel):
    """
    Common fields shared by all notification requests.
    """

    recipient: EmailRecipient

    priority: NotificationPriority = NotificationPriority.NORMAL

    external_reference: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description=(
            "Reference supplied by the calling service, such as a user ID, "
            "order ID, payment ID, or support ticket ID."
        ),
    )

    scheduled_at: datetime | None = Field(
        default=None,
        description=(
            "Optional UTC timestamp indicating when the notification "
            "should be delivered."
        ),
    )

    metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Additional non-template metadata supplied by the calling service."
        ),
    )

    @field_validator("external_reference")
    @classmethod
    def normalize_external_reference(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError("external_reference cannot be blank")

        return normalized


# ============================================================
# Verification email
# ============================================================


class VerificationEmailRequest(BaseNotificationRequest):
    """
    Request sent by the Identity Service after registration or when a user
    requests another verification email.
    """

    user_id: uuid.UUID | None = None

    first_name: str = Field(
        min_length=1,
        max_length=100,
    )

    verification_token: str = Field(
        min_length=8,
        max_length=2048,
    )

    verification_url: HttpUrl | None = Field(
        default=None,
        description=(
            "Optional fully constructed URL. When omitted, the Notification "
            "Service builds the URL from its configuration and token."
        ),
    )

    expires_in_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
    )

    @field_validator("first_name")
    @classmethod
    def normalize_first_name(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("first_name cannot be blank")

        return normalized


# ============================================================
# Password-reset email
# ============================================================


class PasswordResetEmailRequest(BaseNotificationRequest):
    """
    Request sent when a user asks to reset their password.
    """

    user_id: uuid.UUID | None = None

    first_name: str = Field(
        min_length=1,
        max_length=100,
    )

    reset_token: str = Field(
        min_length=8,
        max_length=2048,
    )

    reset_url: HttpUrl | None = Field(
        default=None,
        description=(
            "Optional fully constructed reset URL. When omitted, the service "
            "builds it using its configured marketplace web URL."
        ),
    )

    expires_in_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
    )

    @field_validator("first_name")
    @classmethod
    def normalize_first_name(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("first_name cannot be blank")

        return normalized


# ============================================================
# Password-changed notification
# ============================================================


class PasswordChangedEmailRequest(BaseNotificationRequest):
    """
    Security alert sent after a user's password has been changed.
    """

    user_id: uuid.UUID | None = None

    first_name: str = Field(
        min_length=1,
        max_length=100,
    )

    changed_at: datetime

    ip_address: str | None = Field(
        default=None,
        min_length=3,
        max_length=45,
    )

    user_agent: str | None = Field(
        default=None,
        max_length=500,
    )

    support_url: HttpUrl | None = None

    @field_validator("first_name")
    @classmethod
    def normalize_first_name(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("first_name cannot be blank")

        return normalized


# ============================================================
# Generic templated email
# ============================================================


class TemplatedEmailRequest(BaseNotificationRequest):
    """
    Generic request for sending a registered email template.

    This supports future use cases such as:

    - order confirmation
    - payment confirmation
    - shipment notification
    - refund notification
    - seller onboarding
    """

    template_name: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )

    template_data: dict[str, Any] = Field(
        default_factory=dict,
    )

    subject: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
    )

    sender: EmailSender | None = None

    reply_to_email: str | None = Field(
        default=None,
        min_length=3,
        max_length=320,
    )

    max_retry_count: int | None = Field(
        default=None,
        ge=0,
        le=20,
    )

    headers: dict[str, str] | None = None

    @field_validator("template_name")
    @classmethod
    def normalize_template_name(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("subject")
    @classmethod
    def normalize_subject(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError("subject cannot be blank")

        return normalized


# ============================================================
# Direct email request
# ============================================================


class DirectEmailRequest(BaseNotificationRequest):
    """
    Sends email content supplied directly by a trusted internal service.

    This endpoint should remain protected by service-to-service
    authentication because it bypasses registered templates.
    """

    subject: str = Field(
        min_length=1,
        max_length=300,
    )

    body_html: str | None = Field(
        default=None,
        min_length=1,
    )

    body_text: str | None = Field(
        default=None,
        min_length=1,
    )

    sender: EmailSender | None = None

    reply_to_email: str | None = Field(
        default=None,
        min_length=3,
        max_length=320,
    )

    max_retry_count: int | None = Field(
        default=None,
        ge=0,
        le=20,
    )

    headers: dict[str, str] | None = None

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("subject cannot be blank")

        return normalized

    @model_validator(mode="after")
    def validate_email_body(self) -> DirectEmailRequest:
        if not self.body_html and not self.body_text:
            raise ValueError(
                "At least one of body_html or body_text must be provided"
            )

        return self


# ============================================================
# Notification creation response
# ============================================================


class NotificationQueuedResponse(BaseModel):
    """
    Returned after a notification is persisted and queued.
    """

    notification_id: uuid.UUID

    status: NotificationStatus

    provider: ProviderType

    task_id: str

    message: str

    scheduled_at: datetime | None = None


# ============================================================
# Notification-attempt responses
# ============================================================


class NotificationAttemptResponse(BaseModel):
    """
    Delivery-attempt information returned by the API.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notification_id: uuid.UUID
    attempt_number: int
    provider: ProviderType
    status: NotificationStatus
    provider_message_id: str | None
    response_code: str | None
    response_message: str | None
    latency_ms: int | None
    error_stacktrace: str | None
    created_at: datetime


# ============================================================
# Notification responses
# ============================================================


class NotificationResponse(BaseModel):
    """
    Complete notification representation.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    priority: NotificationPriority
    status: NotificationStatus
    provider: ProviderType

    template_name: str
    subject: str
    recipient: str
    sender: str

    body_html: str | None
    body_text: str | None
    template_data: dict[str, Any] | None

    external_reference: str | None
    provider_message_id: str | None

    retry_count: int
    max_retry_count: int

    scheduled_at: datetime | None
    sent_at: datetime | None
    failed_at: datetime | None

    error_message: str | None
    is_deleted: bool

    created_at: datetime
    updated_at: datetime

    attempts: list[NotificationAttemptResponse] = Field(
        default_factory=list,
    )


class NotificationSummaryResponse(BaseModel):
    """
    Smaller notification representation used in list endpoints.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    priority: NotificationPriority
    status: NotificationStatus
    provider: ProviderType

    template_name: str
    subject: str
    recipient: str

    external_reference: str | None
    retry_count: int

    scheduled_at: datetime | None
    sent_at: datetime | None
    failed_at: datetime | None

    created_at: datetime


class NotificationListResponse(BaseModel):
    """
    Paginated notification list.
    """

    items: list[NotificationSummaryResponse]
    pagination: PaginationMetadata


# ============================================================
# Retry and cancellation requests
# ============================================================


class RetryNotificationRequest(BaseModel):
    """
    Optional overrides when manually retrying a failed notification.
    """

    provider: ProviderType | None = None

    reset_retry_count: bool = False

    delay_seconds: int = Field(
        default=0,
        ge=0,
        le=86400,
    )


class CancelNotificationRequest(BaseModel):
    """
    Optional reason recorded when cancelling a queued notification.
    """

    reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            raise ValueError("reason cannot be blank")

        return normalized


# ============================================================
# Provider result schema
# ============================================================


class ProviderSendResult(BaseModel):
    """
    Normalized result returned by all notification providers.

    SMTP, console, SES, SendGrid, and future providers should return this
    structure through the provider abstraction.
    """

    success: bool

    provider: ProviderType

    provider_message_id: str | None = None

    response_code: str | None = None

    response_message: str | None = None

    latency_ms: int | None = Field(
        default=None,
        ge=0,
    )

    error_message: str | None = None


# ============================================================
# Internal task payload
# ============================================================


class NotificationTaskPayload(BaseModel):
    """
    Minimal payload sent to Celery.

    Only the notification ID is required because the worker retrieves the
    complete notification record from PostgreSQL.
    """

    notification_id: uuid.UUID


# ============================================================
# Health schemas
# ============================================================


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime


class DependencyHealth(BaseModel):
    status: str
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime
    dependencies: dict[str, DependencyHealth]