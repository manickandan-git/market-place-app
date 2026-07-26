from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.models import (
    Notification,
    NotificationAttempt,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
    ProviderType,
)
from app.providers.base import (
    EmailMessage,
    EmailProvider,
    NotificationProviderError,
    PermanentProviderError,
    ProviderResult,
    RetryableProviderError,
)
from app.providers.console import ConsoleEmailProvider
from app.providers.smtp import SMTPEmailProvider
from app.template_service import (
    RenderedTemplate,
    TemplateRenderingError,
    TemplateService,
    UnknownTemplateError,
)

logger = logging.getLogger(__name__)


class EmailServiceError(Exception):
    """
    Base exception for email-service failures.
    """


class NotificationNotFoundError(EmailServiceError):
    """
    Raised when a notification record cannot be found.
    """


class NotificationStateError(EmailServiceError):
    """
    Raised when an operation is invalid for the notification's current state.
    """


class UnsupportedProviderError(EmailServiceError):
    """
    Raised when the configured email provider is unsupported.
    """


class EmailDeliveryError(EmailServiceError):
    """
    Raised when an email delivery attempt fails.
    """

    def __init__(
        self,
        message: str,
        *,
        notification_id: UUID | None = None,
        retryable: bool = False,
        response_code: str | None = None,
    ) -> None:
        super().__init__(message)

        self.notification_id = notification_id
        self.retryable = retryable
        self.response_code = response_code


class EmailService:
    """
    Orchestrates transactional email creation and delivery.

    Responsibilities:

    - render Jinja2 templates
    - create Notification database records
    - select the configured provider
    - deliver email
    - record every provider attempt
    - update notification status
    - classify retryable and permanent failures

    Celery tasks should call this service rather than accessing providers or
    database models directly.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        settings: Settings | None = None,
        template_service: TemplateService | None = None,
        provider: EmailProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()

        self.template_service = (
            template_service
            or TemplateService(settings=self.settings)
        )

        self.provider = provider or self._create_provider()

    async def create_templated_notification(
        self,
        *,
        recipient_email: str,
        template_name: str,
        template_data: dict[str, Any],
        recipient_name: str | None = None,
        subject: str | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
        reply_to_email: str | None = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        external_reference: str | None = None,
        max_retry_count: int | None = None,
        scheduled_at: datetime | None = None,
        headers: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        """
        Render a registered template and persist a pending notification.

        This method does not send the email. The returned notification can be
        passed to a Celery task for asynchronous delivery.
        """

        rendered = self._render_template(
            template_name=template_name,
            template_data=template_data,
            subject=subject,
        )

        notification = Notification(
            type=NotificationType.EMAIL,
            priority=priority,
            status=NotificationStatus.PENDING,
            provider=self.provider.provider_type,
            template_name=rendered.template_name,
            subject=rendered.subject,
            recipient=recipient_email.strip(),
            sender=(
                sender_email
                or str(self.settings.default_from_email)
            ).strip(),
            body_html=rendered.body_html,
            body_text=rendered.body_text,
            template_data={
                **template_data,
                "_recipient_name": recipient_name,
                "_sender_name": (
                    sender_name
                    or self.settings.default_from_name
                ),
                "_reply_to_email": reply_to_email,
                "_headers": headers or {},
                "_metadata": metadata or {},
            },
            external_reference=external_reference,
            retry_count=0,
            max_retry_count=(
                max_retry_count
                if max_retry_count is not None
                else self.settings.notification_max_retries
            ),
            scheduled_at=scheduled_at,
            is_deleted=False,
        )

        self.db.add(notification)

        await self.db.flush()
        await self.db.refresh(notification)

        notification = self._normalize_notification_datetimes(
            notification
        )

        logger.info(
            "Created pending email notification",
            extra={
                "notification_id": str(notification.id),
                "recipient": notification.recipient,
                "template_name": notification.template_name,
                "provider": notification.provider.value,
            },
        )

        return notification

    async def create_direct_notification(
        self,
        *,
        recipient_email: str,
        subject: str,
        body_text: str | None = None,
        body_html: str | None = None,
        recipient_name: str | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
        reply_to_email: str | None = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        external_reference: str | None = None,
        max_retry_count: int | None = None,
        scheduled_at: datetime | None = None,
        headers: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        """
        Persist a direct email that does not use a Jinja2 template.
        """

        if not subject.strip():
            raise EmailServiceError("Email subject is required")

        if not body_text and not body_html:
            raise EmailServiceError(
                "At least one of body_text or body_html is required"
            )

        notification = Notification(
            type=NotificationType.EMAIL,
            priority=priority,
            status=NotificationStatus.PENDING,
            provider=self.provider.provider_type,
            template_name="direct",
            subject=subject.strip(),
            recipient=recipient_email.strip(),
            sender=(
                sender_email
                or str(self.settings.default_from_email)
            ).strip(),
            body_html=body_html,
            body_text=body_text,
            template_data={
                "_recipient_name": recipient_name,
                "_sender_name": (
                    sender_name
                    or self.settings.default_from_name
                ),
                "_reply_to_email": reply_to_email,
                "_headers": headers or {},
                "_metadata": metadata or {},
            },
            external_reference=external_reference,
            retry_count=0,
            max_retry_count=(
                max_retry_count
                if max_retry_count is not None
                else self.settings.notification_max_retries
            ),
            scheduled_at=scheduled_at,
            is_deleted=False,
        )

        self.db.add(notification)

        await self.db.flush()
        await self.db.refresh(notification)

        notification = self._normalize_notification_datetimes(
            notification
        )

        return notification

    async def create_verification_email(
        self,
        *,
        recipient_email: str,
        first_name: str,
        verification_token: str,
        expires_in_minutes: int,
        recipient_name: str | None = None,
        external_reference: str | None = None,
        verification_url: str | None = None,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ) -> Notification:
        """
        Create an account-verification email notification.
        """

        rendered = self.template_service.render_verification_email(
            first_name=first_name,
            verification_token=verification_token,
            expires_in_minutes=expires_in_minutes,
            recipient_email=recipient_email,
            verification_url=verification_url,
        )

        return await self._create_from_rendered_template(
            recipient_email=recipient_email,
            recipient_name=recipient_name or first_name,
            rendered=rendered,
            template_data={
                "first_name": first_name,
                "verification_token": verification_token,
                "verification_url": (
                    verification_url
                    or self.template_service.build_verification_url(
                        verification_token
                    )
                ),
                "expires_in_minutes": expires_in_minutes,
            },
            priority=priority,
            external_reference=external_reference,
        )

    async def create_password_reset_email(
        self,
        *,
        recipient_email: str,
        first_name: str,
        reset_token: str,
        expires_in_minutes: int,
        recipient_name: str | None = None,
        external_reference: str | None = None,
        reset_url: str | None = None,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ) -> Notification:
        """
        Create a password-reset email notification.
        """

        rendered = self.template_service.render_password_reset_email(
            first_name=first_name,
            reset_token=reset_token,
            expires_in_minutes=expires_in_minutes,
            recipient_email=recipient_email,
            reset_url=reset_url,
        )

        return await self._create_from_rendered_template(
            recipient_email=recipient_email,
            recipient_name=recipient_name or first_name,
            rendered=rendered,
            template_data={
                "first_name": first_name,
                "reset_token": reset_token,
                "reset_url": (
                    reset_url
                    or self.template_service.build_password_reset_url(
                        reset_token
                    )
                ),
                "expires_in_minutes": expires_in_minutes,
            },
            priority=priority,
            external_reference=external_reference,
        )

    async def create_password_changed_email(
        self,
        *,
        recipient_email: str,
        first_name: str,
        changed_at: datetime,
        recipient_name: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        external_reference: str | None = None,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ) -> Notification:
        """
        Create a password-changed security notification.
        """

        rendered = self.template_service.render_password_changed_email(
            first_name=first_name,
            changed_at=changed_at,
            recipient_email=recipient_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return await self._create_from_rendered_template(
            recipient_email=recipient_email,
            recipient_name=recipient_name or first_name,
            rendered=rendered,
            template_data={
                "first_name": first_name,
                "changed_at": changed_at.isoformat(),
                "ip_address": ip_address,
                "user_agent": user_agent,
            },
            priority=priority,
            external_reference=external_reference,
        )

    async def send_notification(
        self,
        notification_id: UUID,
    ) -> Notification:
        """
        Deliver a pending or retrying notification.

        The transaction is committed after the attempt is recorded and the
        notification status is updated.
        """

        notification = await self.get_notification(
            notification_id,
            include_attempts=True,
            for_update=True,
        )

        self._validate_delivery_state(notification)

        scheduled_at = notification.scheduled_at
        if (
            isinstance(scheduled_at, datetime)
            and scheduled_at.tzinfo is None
        ):
            scheduled_at = scheduled_at.replace(
                tzinfo=timezone.utc
            )

        if (
            scheduled_at is not None
            and scheduled_at > self._utc_now()
        ):
            raise NotificationStateError(
                "Notification is scheduled for future delivery"
            )

        attempt_number = len(notification.attempts) + 1

        notification.status = NotificationStatus.PROCESSING
        notification.error_message = None

        await self.db.flush()

        message = self._build_email_message(notification)

        started_at = time.perf_counter()

        try:
            result = self.provider.send(message)

            latency_ms = result.latency_ms or self._elapsed_ms(
                started_at
            )

            self._record_success(
                notification=notification,
                attempt_number=attempt_number,
                result=result,
                latency_ms=latency_ms,
            )

            await self.db.commit()

            return await self.get_notification(
                notification.id,
                include_attempts=True,
            )

        except NotificationProviderError as exc:
            latency_ms = self._elapsed_ms(started_at)

            self._record_provider_failure(
                notification=notification,
                attempt_number=attempt_number,
                error=exc,
                latency_ms=latency_ms,
            )

            await self.db.commit()

            raise EmailDeliveryError(
                exc.message,
                notification_id=notification.id,
                retryable=exc.retryable,
                response_code=exc.response_code,
            ) from exc

        except Exception as exc:
            latency_ms = self._elapsed_ms(started_at)

            logger.exception(
                "Unexpected email delivery failure",
                extra={
                    "notification_id": str(notification.id),
                    "provider": self.provider.provider_type.value,
                },
            )

            unexpected_error = RetryableProviderError(
                f"Unexpected provider failure: {exc}",
                response_code="UNEXPECTED_PROVIDER_ERROR",
            )

            self._record_provider_failure(
                notification=notification,
                attempt_number=attempt_number,
                error=unexpected_error,
                latency_ms=latency_ms,
                error_stacktrace=traceback.format_exc(),
            )

            await self.db.commit()

            raise EmailDeliveryError(
                str(exc),
                notification_id=notification.id,
                retryable=True,
                response_code="UNEXPECTED_PROVIDER_ERROR",
            ) from exc

    async def retry_notification(
        self,
        notification_id: UUID,
    ) -> Notification:
        """
        Move an eligible failed notification into retrying state.
        """

        notification = await self.get_notification(
            notification_id,
            include_attempts=True,
            for_update=True,
        )

        if notification.status not in {
            NotificationStatus.FAILED,
            NotificationStatus.RETRYING,
        }:
            raise NotificationStateError(
                "Only failed or retrying notifications can be retried"
            )

        if notification.retry_count >= notification.max_retry_count:
            raise NotificationStateError(
                "Maximum retry count has been reached"
            )

        notification.status = NotificationStatus.RETRYING
        notification.error_message = None
        notification.failed_at = None

        await self.db.commit()

        return await self.get_notification(
            notification.id,
            include_attempts=True,
        )

    async def cancel_notification(
        self,
        notification_id: UUID,
    ) -> Notification:
        """
        Cancel a notification that has not already been sent.
        """

        notification = await self.get_notification(
            notification_id,
            include_attempts=True,
            for_update=True,
        )

        if notification.status == NotificationStatus.SENT:
            raise NotificationStateError(
                "A sent notification cannot be cancelled"
            )

        if notification.status == NotificationStatus.CANCELLED:
            return notification

        if notification.status == NotificationStatus.PROCESSING:
            raise NotificationStateError(
                "A notification currently being processed cannot be cancelled"
            )

        notification.status = NotificationStatus.CANCELLED
        notification.error_message = "Cancelled by request"

        await self.db.commit()

        return await self.get_notification(
            notification.id,
            include_attempts=True,
        )

    async def get_notification(
        self,
        notification_id: UUID,
        *,
        include_attempts: bool = False,
        for_update: bool = False,
    ) -> Notification:
        """
        Retrieve one non-deleted notification.
        """

        statement = select(Notification).where(
            Notification.id == notification_id,
            Notification.is_deleted.is_(False),
        )
        statement = statement.execution_options(
            populate_existing=True
        )

        if include_attempts:
            statement = statement.options(
                selectinload(Notification.attempts)
            )

        if for_update:
            statement = statement.with_for_update()

        result = await self.db.execute(statement)
        notification = result.scalar_one_or_none()

        if notification is None:
            raise NotificationNotFoundError(
                f"Notification '{notification_id}' was not found"
            )

        return notification

    async def list_notifications(
        self,
        *,
        status: NotificationStatus | None = None,
        recipient: str | None = None,
        provider: ProviderType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """
        Return notifications using common operational filters.
        """

        if limit < 1 or limit > 200:
            raise EmailServiceError(
                "limit must be between 1 and 200"
            )

        if offset < 0:
            raise EmailServiceError(
                "offset cannot be negative"
            )

        statement = (
            select(Notification)
            .where(Notification.is_deleted.is_(False))
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if status is not None:
            statement = statement.where(
                Notification.status == status
            )

        if recipient:
            statement = statement.where(
                Notification.recipient == recipient.strip()
            )

        if provider is not None:
            statement = statement.where(
                Notification.provider == provider
            )

        result = await self.db.execute(statement)

        return list(result.scalars().all())

    async def _create_from_rendered_template(
        self,
        *,
        recipient_email: str,
        recipient_name: str | None,
        rendered: RenderedTemplate,
        template_data: dict[str, Any],
        priority: NotificationPriority,
        external_reference: str | None,
    ) -> Notification:
        notification = Notification(
            type=NotificationType.EMAIL,
            priority=priority,
            status=NotificationStatus.PENDING,
            provider=self.provider.provider_type,
            template_name=rendered.template_name,
            subject=rendered.subject,
            recipient=recipient_email.strip(),
            sender=str(self.settings.default_from_email),
            body_html=rendered.body_html,
            body_text=rendered.body_text,
            template_data={
                **template_data,
                "_recipient_name": recipient_name,
                "_sender_name": self.settings.default_from_name,
                "_reply_to_email": str(
                    self.settings.support_email
                ),
                "_headers": {},
                "_metadata": {},
            },
            external_reference=external_reference,
            retry_count=0,
            max_retry_count=self.settings.notification_max_retries,
            scheduled_at=None,
            is_deleted=False,
        )

        self.db.add(notification)

        await self.db.flush()
        await self.db.refresh(notification)

        notification = self._normalize_notification_datetimes(
            notification
        )

        return notification

    def _normalize_notification_datetimes(
        self,
        notification: Notification,
    ) -> Notification:
        for field_name in (
            "scheduled_at",
            "sent_at",
            "failed_at",
            "created_at",
            "updated_at",
        ):
            value = getattr(notification, field_name, None)

            if (
                isinstance(value, datetime)
                and value.tzinfo is None
            ):
                setattr(
                    notification,
                    field_name,
                    value.replace(tzinfo=timezone.utc),
                )

        return notification

    def _render_template(
        self,
        *,
        template_name: str,
        template_data: dict[str, Any],
        subject: str | None,
    ) -> RenderedTemplate:
        try:
            return self.template_service.render(
                template_name,
                template_data,
                subject=subject,
            )

        except UnknownTemplateError as exc:
            raise EmailServiceError(str(exc)) from exc

        except TemplateRenderingError as exc:
            raise EmailServiceError(str(exc)) from exc

    def _create_provider(self) -> EmailProvider:
        provider_name = self._configured_provider_name()

        if provider_name == ProviderType.CONSOLE.value:
            return ConsoleEmailProvider()

        if provider_name == ProviderType.SMTP.value:
            return SMTPEmailProvider()

        raise UnsupportedProviderError(
            f"Unsupported email provider: {provider_name}"
        )

    def _configured_provider_name(self) -> str:
        configured_provider = self.settings.email_provider

        if isinstance(configured_provider, ProviderType):
            return configured_provider.value

        return str(configured_provider).strip().upper()

    def _build_email_message(
        self,
        notification: Notification,
    ) -> EmailMessage:
        internal_data = notification.template_data or {}

        headers = internal_data.get("_headers") or {}
        metadata = internal_data.get("_metadata") or {}

        return EmailMessage(
            recipient_email=notification.recipient,
            recipient_name=internal_data.get("_recipient_name"),
            sender_email=notification.sender,
            sender_name=(
                internal_data.get("_sender_name")
                or self.settings.default_from_name
            ),
            reply_to_email=internal_data.get(
                "_reply_to_email"
            ),
            subject=notification.subject,
            body_html=notification.body_html,
            body_text=notification.body_text,
            headers=dict(headers),
            metadata={
                **dict(metadata),
                "notification_id": str(notification.id),
                "template_name": notification.template_name,
                "external_reference": (
                    notification.external_reference
                ),
            },
        )

    def _record_success(
        self,
        *,
        notification: Notification,
        attempt_number: int,
        result: ProviderResult,
        latency_ms: int,
    ) -> None:
        now = self._utc_now()

        attempt = NotificationAttempt(
            notification_id=notification.id,
            attempt_number=attempt_number,
            provider=result.provider,
            status=NotificationStatus.SENT,
            provider_message_id=result.provider_message_id,
            response_code=result.response_code,
            response_message=result.response_message,
            latency_ms=latency_ms,
            error_stacktrace=None,
        )

        self.db.add(attempt)

        notification.status = NotificationStatus.SENT
        notification.provider = result.provider
        notification.provider_message_id = (
            result.provider_message_id
        )
        notification.sent_at = now
        notification.failed_at = None
        notification.error_message = None

        logger.info(
            "Email notification sent",
            extra={
                "notification_id": str(notification.id),
                "provider": result.provider.value,
                "provider_message_id": result.provider_message_id,
                "latency_ms": latency_ms,
            },
        )

    def _record_provider_failure(
        self,
        *,
        notification: Notification,
        attempt_number: int,
        error: NotificationProviderError,
        latency_ms: int,
        error_stacktrace: str | None = None,
    ) -> None:
        now = self._utc_now()

        notification.retry_count += 1

        can_retry = (
            error.retryable
            and notification.retry_count
            < notification.max_retry_count
        )

        resulting_status = (
            NotificationStatus.RETRYING
            if can_retry
            else NotificationStatus.FAILED
        )

        attempt = NotificationAttempt(
            notification_id=notification.id,
            attempt_number=attempt_number,
            provider=self.provider.provider_type,
            status=resulting_status,
            provider_message_id=None,
            response_code=error.response_code,
            response_message=error.message,
            latency_ms=latency_ms,
            error_stacktrace=error_stacktrace,
        )

        self.db.add(attempt)

        notification.status = resulting_status
        notification.error_message = error.message
        notification.failed_at = now

        logger.warning(
            "Email notification delivery failed",
            extra={
                "notification_id": str(notification.id),
                "provider": self.provider.provider_type.value,
                "retryable": error.retryable,
                "retry_count": notification.retry_count,
                "max_retry_count": notification.max_retry_count,
                "status": resulting_status.value,
                "response_code": error.response_code,
            },
        )

    @staticmethod
    def _validate_delivery_state(
        notification: Notification,
    ) -> None:
        if notification.type != NotificationType.EMAIL:
            raise NotificationStateError(
                "The notification is not an email notification"
            )

        if notification.status == NotificationStatus.SENT:
            raise NotificationStateError(
                "Notification has already been sent"
            )

        if notification.status == NotificationStatus.CANCELLED:
            raise NotificationStateError(
                "Cancelled notification cannot be sent"
            )

        if notification.status == NotificationStatus.PROCESSING:
            raise NotificationStateError(
                "Notification is already being processed"
            )

        if notification.status not in {
            NotificationStatus.PENDING,
            NotificationStatus.RETRYING,
            NotificationStatus.FAILED,
        }:
            raise NotificationStateError(
                f"Notification cannot be sent from status "
                f"'{notification.status.value}'"
            )

        if (
            notification.status == NotificationStatus.FAILED
            and notification.retry_count
            >= notification.max_retry_count
        ):
            raise NotificationStateError(
                "Maximum retry count has been reached"
            )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(
            0,
            int((time.perf_counter() - started_at) * 1000),
        )