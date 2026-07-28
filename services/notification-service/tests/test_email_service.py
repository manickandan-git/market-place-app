from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.email_service import (
    EmailDeliveryError,
    EmailService,
    NotificationNotFoundError,
    NotificationStateError,
)
from app.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    ProviderType,
)
from app.providers.base import EmailMessage, ProviderResult
from tests.conftest import MockEmailProvider

pytestmark = pytest.mark.asyncio


def create_email_service(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> EmailService:
    """
    Create an EmailService configured with the mock provider.

    This helper assumes EmailService accepts an optional provider argument.
    When the current EmailService constructor does not accept that argument,
    instantiate the service normally and assign the provider afterward.
    """

    try:
        return EmailService(
            db=db_session,
            provider=mock_email_provider,
        )
    except TypeError:
        service = EmailService(db_session)
        service.provider = mock_email_provider
        return service


async def test_create_direct_notification(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.create_direct_notification(
        recipient_email="customer@example.com",
        recipient_name="Marketplace Customer",
        subject="Order confirmation",
        body_text="Your order has been received.",
        body_html="<p>Your order has been received.</p>",
        sender_email="no-reply@marketplace.local",
        sender_name="Marketplace",
        reply_to_email="support@marketplace.local",
        priority=NotificationPriority.NORMAL,
        external_reference="order-1001",
        max_retry_count=3,
        headers={
            "X-Notification-Source": "test-suite",
        },
        metadata={
            "order_id": "1001",
        },
    )

    assert notification.id is not None
    assert notification.status == NotificationStatus.PENDING
    assert notification.priority == NotificationPriority.NORMAL
    assert notification.provider == ProviderType.CONSOLE
    assert notification.recipient == "customer@example.com"
    assert notification.recipient_name == "Marketplace Customer"
    assert notification.subject == "Order confirmation"
    assert notification.body_text == "Your order has been received."
    assert notification.body_html == (
        "<p>Your order has been received.</p>"
    )
    assert notification.sender == "no-reply@marketplace.local"
    assert notification.sender_name == "Marketplace"
    assert notification.reply_to_email == "support@marketplace.local"
    assert notification.external_reference == "order-1001"
    assert notification.retry_count == 0
    assert notification.max_retry_count == 3


async def test_create_scheduled_direct_notification(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    scheduled_at = datetime.now(UTC) + timedelta(hours=2)

    notification = await service.create_direct_notification(
        recipient_email="customer@example.com",
        recipient_name="Marketplace Customer",
        subject="Scheduled notification",
        body_text="This message is scheduled.",
        body_html="<p>This message is scheduled.</p>",
        scheduled_at=scheduled_at,
    )

    assert notification.status == NotificationStatus.PENDING
    assert notification.scheduled_at is not None

    difference = abs(
        (
            notification.scheduled_at - scheduled_at
        ).total_seconds()
    )

    assert difference < 1


async def test_create_direct_notification_requires_content(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(
        Exception,
        match="body|content|HTML|text",
    ):
        await service.create_direct_notification(
            recipient_email="customer@example.com",
            recipient_name="Marketplace Customer",
            subject="Missing body",
            body_text=None,
            body_html=None,
        )


async def test_create_verification_email(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.create_verification_email(
        recipient_email="customer@example.com",
        recipient_name="Marketplace Customer",
        first_name="Customer",
        verification_token="verify-token-123",
        verification_url=(
            "http://localhost:3000/verify-email"
            "?token=verify-token-123"
        ),
        expires_in_minutes=30,
        external_reference="user-123",
        priority=NotificationPriority.HIGH,
    )

    assert notification.id is not None
    assert notification.template_name == "verification"
    assert notification.status == NotificationStatus.PENDING
    assert notification.priority == NotificationPriority.HIGH
    assert notification.recipient == "customer@example.com"
    assert notification.external_reference == "user-123"

    assert "verify" in notification.subject.lower()
    assert "Customer" in notification.body_text
    assert "verify-token-123" in notification.body_text
    assert "verify-token-123" in notification.body_html


async def test_create_password_reset_email(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.create_password_reset_email(
        recipient_email="customer@example.com",
        recipient_name="Marketplace Customer",
        first_name="Customer",
        reset_token="reset-token-123",
        reset_url=(
            "http://localhost:3000/reset-password"
            "?token=reset-token-123"
        ),
        expires_in_minutes=20,
        external_reference="user-123",
        priority=NotificationPriority.HIGH,
    )

    assert notification.id is not None
    assert notification.template_name == "password_reset"
    assert notification.status == NotificationStatus.PENDING
    assert notification.priority == NotificationPriority.HIGH

    assert "password" in notification.subject.lower()
    assert "reset-token-123" in notification.body_text
    assert "reset-token-123" in notification.body_html


async def test_create_password_changed_email(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    changed_at = datetime.now(UTC)

    notification = await service.create_password_changed_email(
        recipient_email="customer@example.com",
        recipient_name="Marketplace Customer",
        first_name="Customer",
        changed_at=changed_at,
        ip_address="127.0.0.1",
        user_agent="pytest-test-client",
        external_reference="user-123",
        priority=NotificationPriority.HIGH,
    )

    assert notification.id is not None
    assert notification.template_name == "password_changed"
    assert notification.status == NotificationStatus.PENDING
    assert notification.priority == NotificationPriority.HIGH

    assert "password" in notification.subject.lower()
    assert "127.0.0.1" in notification.body_text
    assert "pytest-test-client" in notification.body_text
    assert "127.0.0.1" in notification.body_html


async def test_send_pending_notification_successfully(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    result = await service.send_notification(
        pending_notification.id
    )

    assert result.status == NotificationStatus.SENT
    assert result.sent_at is not None
    assert result.failed_at is None
    assert result.provider_message_id is not None
    assert result.provider_message_id.startswith("mock-")
    assert result.error_message in (None, "")

    assert len(mock_email_provider.sent_messages) == 1

    sent_message = mock_email_provider.sent_messages[0]

    assert sent_message.recipient_email == (
        pending_notification.recipient
    )
    assert sent_message.subject == pending_notification.subject
    assert sent_message.body_text == pending_notification.body_text
    assert sent_message.body_html == pending_notification.body_html


async def test_send_notification_creates_delivery_attempt(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.send_notification(
        pending_notification.id
    )

    loaded = await service.get_notification(
        notification.id,
        include_attempts=True,
    )

    assert len(loaded.attempts) == 1

    attempt = loaded.attempts[0]

    assert attempt.success is True
    assert attempt.provider == ProviderType.CONSOLE
    assert attempt.provider_message_id is not None
    assert attempt.error_message in (None, "")
    assert attempt.attempt_number == 1


async def test_worker_crash_mid_send_blocks_duplicate_redelivery(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    """
    If the process is killed after the provider accepts the message but
    before the success commit (simulated here by an exception that escapes
    the `except Exception` handlers, like a real worker kill would), the
    PROCESSING transition must already be durable so a Celery redelivery of
    the same task cannot send the notification a second time.
    """

    def crash_during_send(
        message: EmailMessage,
    ) -> ProviderResult:
        raise asyncio.CancelledError("worker killed mid-send")

    mock_email_provider.send = crash_during_send  # type: ignore[method-assign]

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(asyncio.CancelledError):
        await service.send_notification(pending_notification.id)

    notification = await service.get_notification(
        pending_notification.id,
        include_attempts=True,
    )

    assert notification.status == NotificationStatus.PROCESSING

    with pytest.raises(
        NotificationStateError,
        match="already being processed",
    ):
        await service.send_notification(pending_notification.id)


async def test_send_notification_with_retryable_failure(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    mock_email_provider.should_fail = True
    mock_email_provider.failure_retryable = True
    mock_email_provider.failure_message = (
        "Temporary SMTP connection failure"
    )
    mock_email_provider.response_code = "421"

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(EmailDeliveryError) as exception_info:
        await service.send_notification(
            pending_notification.id
        )

    error = exception_info.value

    assert error.retryable is True
    assert "Temporary SMTP" in str(error)

    notification = await service.get_notification(
        pending_notification.id,
        include_attempts=True,
    )

    assert notification.status in {
        NotificationStatus.FAILED,
        NotificationStatus.RETRYING,
    }
    assert notification.failed_at is not None
    assert notification.retry_count >= 1
    assert notification.error_message is not None

    assert len(notification.attempts) == 1
    assert notification.attempts[0].success is False
    assert notification.attempts[0].retryable is True


async def test_send_notification_with_permanent_failure(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    mock_email_provider.should_fail = True
    mock_email_provider.failure_retryable = False
    mock_email_provider.failure_message = (
        "Recipient address rejected"
    )
    mock_email_provider.response_code = "550"

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(EmailDeliveryError) as exception_info:
        await service.send_notification(
            pending_notification.id
        )

    error = exception_info.value

    assert error.retryable is False
    assert "Recipient address rejected" in str(error)

    notification = await service.get_notification(
        pending_notification.id,
        include_attempts=True,
    )

    assert notification.status == NotificationStatus.FAILED
    assert notification.failed_at is not None
    assert notification.error_message is not None

    assert len(notification.attempts) == 1
    assert notification.attempts[0].success is False
    assert notification.attempts[0].retryable is False


async def test_send_notification_unexpected_bug_is_not_retryable(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    """
    An exception that isn't a NotificationProviderError indicates a
    programming defect (providers are contracted to wrap every delivery
    failure), not a transient delivery failure. It must fail immediately
    instead of consuming the notification's retry budget on attempts that
    can never succeed.
    """

    def buggy_send(message: EmailMessage) -> ProviderResult:
        raise TypeError("provider contract violated")

    mock_email_provider.send = buggy_send  # type: ignore[method-assign]

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(EmailDeliveryError) as exception_info:
        await service.send_notification(
            pending_notification.id
        )

    error = exception_info.value

    assert error.retryable is False

    notification = await service.get_notification(
        pending_notification.id,
        include_attempts=True,
    )

    assert notification.status == NotificationStatus.FAILED
    assert len(notification.attempts) == 1
    assert notification.attempts[0].retryable is False


async def test_send_notification_message_build_bug_is_recorded(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    """
    A bug while building the outgoing message must not leave the
    notification wedged in PROCESSING: it happens after the PROCESSING
    transition is committed, so it needs to be caught and recorded like any
    other internal defect, not left to propagate uncaught.
    """

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    def buggy_build_email_message(
        notification: Notification,
    ) -> EmailMessage:
        raise TypeError("malformed template_data")

    service._build_email_message = (  # type: ignore[method-assign]
        buggy_build_email_message
    )

    with pytest.raises(EmailDeliveryError) as exception_info:
        await service.send_notification(
            pending_notification.id
        )

    assert exception_info.value.retryable is False

    notification = await service.get_notification(
        pending_notification.id,
        include_attempts=True,
    )

    assert notification.status == NotificationStatus.FAILED


async def test_send_notification_not_found(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(NotificationNotFoundError):
        await service.send_notification(uuid4())


async def test_send_already_sent_notification_is_rejected(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    sent_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(NotificationStateError):
        await service.send_notification(
            sent_notification.id
        )

    assert mock_email_provider.sent_messages == []


async def test_send_cancelled_notification_is_rejected(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    pending_notification.status = NotificationStatus.CANCELLED
    await db_session.flush()

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(NotificationStateError):
        await service.send_notification(
            pending_notification.id
        )

    assert mock_email_provider.sent_messages == []


async def test_send_future_scheduled_notification_is_rejected(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    pending_notification.scheduled_at = (
        datetime.now(UTC) + timedelta(hours=1)
    )
    await db_session.flush()

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(
        NotificationStateError,
        match="scheduled|not ready|future",
    ):
        await service.send_notification(
            pending_notification.id
        )

    assert mock_email_provider.sent_messages == []


async def test_retry_failed_notification(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    failed_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    previous_retry_count = failed_notification.retry_count

    notification = await service.retry_notification(
        failed_notification.id
    )

    assert notification.status in {
        NotificationStatus.PENDING,
        NotificationStatus.RETRYING,
    }
    assert notification.failed_at is None
    assert notification.error_message in (None, "")

    # Some implementations increment retry_count when preparing a retry,
    # while others increment it only when the next provider attempt occurs.
    assert notification.retry_count in {
        previous_retry_count,
        previous_retry_count + 1,
    }


async def test_retry_sent_notification_is_rejected(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    sent_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(NotificationStateError):
        await service.retry_notification(
            sent_notification.id
        )


async def test_retry_notification_at_maximum_attempts_is_rejected(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    failed_notification: Notification,
) -> None:
    failed_notification.retry_count = 3
    failed_notification.max_retry_count = 3

    await db_session.flush()

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(
        NotificationStateError,
        match="retry|maximum|max",
    ):
        await service.retry_notification(
            failed_notification.id
        )


async def test_retry_notification_reset_retry_count_bypasses_maximum(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    failed_notification: Notification,
) -> None:
    failed_notification.retry_count = 3
    failed_notification.max_retry_count = 3

    await db_session.flush()

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.retry_notification(
        failed_notification.id,
        reset_retry_count=True,
    )

    assert notification.status in {
        NotificationStatus.PENDING,
        NotificationStatus.RETRYING,
    }
    assert notification.retry_count == 0


async def test_cancel_pending_notification(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.cancel_notification(
        pending_notification.id
    )

    assert notification.status == NotificationStatus.CANCELLED


async def test_cancel_failed_notification(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    failed_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.cancel_notification(
        failed_notification.id
    )

    assert notification.status == NotificationStatus.CANCELLED


async def test_cancel_sent_notification_is_rejected(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    sent_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(NotificationStateError):
        await service.cancel_notification(
            sent_notification.id
        )


async def test_cancel_notification_not_found(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(NotificationNotFoundError):
        await service.cancel_notification(uuid4())


async def test_get_notification(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.get_notification(
        pending_notification.id
    )

    assert notification.id == pending_notification.id
    assert notification.subject == pending_notification.subject
    assert notification.recipient == pending_notification.recipient


async def test_get_notification_not_found(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(NotificationNotFoundError):
        await service.get_notification(uuid4())


async def test_get_soft_deleted_notification_is_not_found(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
) -> None:
    pending_notification.is_deleted = True
    await db_session.flush()

    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    with pytest.raises(NotificationNotFoundError):
        await service.get_notification(
            pending_notification.id
        )


async def test_list_notifications(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
    failed_notification: Notification,
    sent_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notifications = await service.list_notifications(
        limit=10,
        offset=0,
    )

    notification_ids = {
        notification.id
        for notification in notifications
    }

    assert pending_notification.id in notification_ids
    assert failed_notification.id in notification_ids
    assert sent_notification.id in notification_ids


async def test_list_notifications_filtered_by_status(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
    pending_notification: Notification,
    failed_notification: Notification,
    sent_notification: Notification,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notifications = await service.list_notifications(
        status=NotificationStatus.FAILED,
        limit=10,
        offset=0,
    )

    assert notifications
    assert all(
        notification.status == NotificationStatus.FAILED
        for notification in notifications
    )

    notification_ids = {
        notification.id
        for notification in notifications
    }

    assert failed_notification.id in notification_ids
    assert pending_notification.id not in notification_ids
    assert sent_notification.id not in notification_ids


async def test_list_notifications_filtered_by_recipient(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    first = await service.create_direct_notification(
        recipient_email="first@example.com",
        subject="First notification",
        body_text="First body",
    )

    second = await service.create_direct_notification(
        recipient_email="second@example.com",
        subject="Second notification",
        body_text="Second body",
    )

    await db_session.flush()

    notifications = await service.list_notifications(
        recipient="first@example.com",
        limit=10,
        offset=0,
    )

    notification_ids = {
        notification.id
        for notification in notifications
    }

    assert first.id in notification_ids
    assert second.id not in notification_ids


async def test_list_notifications_applies_pagination(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    for index in range(5):
        await service.create_direct_notification(
            recipient_email=f"customer{index}@example.com",
            subject=f"Notification {index}",
            body_text=f"Body {index}",
        )

    await db_session.flush()

    first_page = await service.list_notifications(
        limit=2,
        offset=0,
    )

    second_page = await service.list_notifications(
        limit=2,
        offset=2,
    )

    assert len(first_page) == 2
    assert len(second_page) == 2

    first_page_ids = {
        notification.id
        for notification in first_page
    }

    second_page_ids = {
        notification.id
        for notification in second_page
    }

    assert first_page_ids.isdisjoint(second_page_ids)


async def test_provider_message_contains_custom_headers(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.create_direct_notification(
        recipient_email="customer@example.com",
        recipient_name="Marketplace Customer",
        subject="Header test",
        body_text="Testing custom headers.",
        headers={
            "X-Correlation-ID": "correlation-123",
            "X-Source-Service": "identity-service",
        },
    )

    await service.send_notification(notification.id)

    assert len(mock_email_provider.sent_messages) == 1

    message = mock_email_provider.sent_messages[0]

    assert message.headers["X-Correlation-ID"] == (
        "correlation-123"
    )
    assert message.headers["X-Source-Service"] == (
        "identity-service"
    )


async def test_provider_message_contains_metadata(
    db_session: AsyncSession,
    mock_email_provider: MockEmailProvider,
) -> None:
    service = create_email_service(
        db_session,
        mock_email_provider,
    )

    notification = await service.create_direct_notification(
        recipient_email="customer@example.com",
        subject="Metadata test",
        body_text="Testing metadata.",
        metadata={
            "user_id": "user-123",
            "tenant_id": "tenant-456",
        },
    )

    await service.send_notification(notification.id)

    assert len(mock_email_provider.sent_messages) == 1

    message = mock_email_provider.sent_messages[0]

    assert message.metadata["user_id"] == "user-123"
    assert message.metadata["tenant_id"] == "tenant-456"
