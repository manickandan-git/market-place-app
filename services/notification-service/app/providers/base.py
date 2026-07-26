from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models import ProviderType


@dataclass(slots=True)
class EmailMessage:
    """
    Provider-neutral email message.

    The Notification Service creates this object after templates have been
    rendered. Each provider translates it into its own transport format.
    """

    recipient_email: str
    subject: str

    sender_email: str
    sender_name: str | None = None

    recipient_name: str | None = None

    body_html: str | None = None
    body_text: str | None = None

    reply_to_email: str | None = None

    headers: dict[str, str] = field(default_factory=dict)

    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """
        Validate the provider-neutral email before delivery.
        """

        if not self.recipient_email.strip():
            raise ValueError("recipient_email is required")

        if not self.sender_email.strip():
            raise ValueError("sender_email is required")

        if not self.subject.strip():
            raise ValueError("subject is required")

        if not self.body_html and not self.body_text:
            raise ValueError(
                "At least one of body_html or body_text is required"
            )


@dataclass(slots=True)
class ProviderResult:
    """
    Normalized result returned by every email provider.
    """

    success: bool
    provider: ProviderType

    provider_message_id: str | None = None

    response_code: str | None = None
    response_message: str | None = None

    latency_ms: int | None = None

    error_message: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)


class NotificationProviderError(Exception):
    """
    Base exception for notification-provider failures.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        response_code: str | None = None,
    ) -> None:
        super().__init__(message)

        self.message = message
        self.retryable = retryable
        self.response_code = response_code


class RetryableProviderError(NotificationProviderError):
    """
    Raised when delivery may succeed if attempted again.

    Examples:

    - temporary SMTP connection failure
    - provider timeout
    - provider rate limit
    - temporary service outage
    """

    def __init__(
        self,
        message: str,
        *,
        response_code: str | None = None,
    ) -> None:
        super().__init__(
            message,
            retryable=True,
            response_code=response_code,
        )


class PermanentProviderError(NotificationProviderError):
    """
    Raised when retrying is unlikely to succeed.

    Examples:

    - malformed email address
    - rejected sender domain
    - unsupported message format
    - permanent SMTP rejection
    """

    def __init__(
        self,
        message: str,
        *,
        response_code: str | None = None,
    ) -> None:
        super().__init__(
            message,
            retryable=False,
            response_code=response_code,
        )


class EmailProvider(ABC):
    """
    Abstract contract implemented by every email provider.

    Implementations may use synchronous libraries internally because email
    delivery occurs inside a Celery worker. The service layer depends only on
    this interface and does not need to know whether the provider is SMTP,
    console logging, SES, SendGrid, or another transport.
    """

    provider_type: ProviderType

    @abstractmethod
    def send(self, message: EmailMessage) -> ProviderResult:
        """
        Deliver one email message.

        Implementations should:

        1. Validate provider-specific configuration.
        2. Send the email.
        3. Return a normalized ProviderResult on success.
        4. Raise RetryableProviderError for temporary failures.
        5. Raise PermanentProviderError for permanent failures.
        """

        raise NotImplementedError

    def health_check(self) -> bool:
        """
        Optionally verify provider availability.

        Providers that support a meaningful connectivity check can override
        this method. The default implementation indicates that configuration
        loading succeeded.
        """

        return True

    def validate_message(self, message: EmailMessage) -> None:
        """
        Run shared message validation before provider-specific delivery.
        """

        message.validate()