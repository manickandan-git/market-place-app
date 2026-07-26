from __future__ import annotations

import hmac
from datetime import datetime, timezone
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.email_service import (
    EmailDeliveryError,
    EmailService,
    EmailServiceError,
    NotificationNotFoundError,
    NotificationStateError,
)
from app.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    ProviderType,
)
from app.schemas import (
    CancelNotificationRequest,
    DirectEmailRequest,
    MessageResponse,
    NotificationListResponse,
    NotificationQueuedResponse,
    NotificationResponse,
    NotificationSummaryResponse,
    PaginationMetadata,
    PasswordChangedEmailRequest,
    PasswordResetEmailRequest,
    RetryNotificationRequest,
    TemplatedEmailRequest,
    VerificationEmailRequest,
)
from app.tasks import retry_notification, send_notification

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


def get_email_service(
    db: AsyncSession = Depends(get_db),
) -> EmailService:
    """
    Create an EmailService for the current request.
    """

    return EmailService(db)


def require_internal_api_key(
    x_internal_api_key: str | None = Header(
        default=None,
        alias="X-Internal-API-Key",
    ),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Protect internal service-to-service endpoints.

    The Identity Service and other trusted Marketplace services must send:

        X-Internal-API-Key: <configured key>
    """

    configured_key = settings.internal_api_key

    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal API authentication is not configured",
        )

    if not x_internal_api_key or not hmac.compare_digest(
        x_internal_api_key, configured_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API key",
        )


@router.post(
    "/email/verification",
    response_model=NotificationQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_key)],
)
async def queue_verification_email(
    request: VerificationEmailRequest,
    service: EmailService = Depends(get_email_service),
) -> NotificationQueuedResponse:
    """
    Queue an account-verification email.
    """

    try:
        notification = await service.create_verification_email(
            recipient_email=str(request.recipient.email),
            recipient_name=request.recipient.name,
            first_name=request.first_name,
            verification_token=request.verification_token,
            verification_url=(
                str(request.verification_url)
                if request.verification_url
                else None
            ),
            expires_in_minutes=request.expires_in_minutes,
            external_reference=request.external_reference,
            priority=request.priority,
        )

        await service.db.commit()

        task = send_notification.apply_async(
            args=[str(notification.id)],
            task_id=f"notification-{notification.id}",
        )

        return NotificationQueuedResponse(
            notification_id=notification.id,
            status=notification.status,
            provider=notification.provider,
            task_id=task.id,
            message="Verification email queued successfully",
        )

    except EmailServiceError as exc:
        await service.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception:
        await service.db.rollback()
        raise


@router.post(
    "/email/password-reset",
    response_model=NotificationQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_key)],
)
async def queue_password_reset_email(
    request: PasswordResetEmailRequest,
    service: EmailService = Depends(get_email_service),
) -> NotificationQueuedResponse:
    """
    Queue a password-reset email.
    """

    try:
        notification = await service.create_password_reset_email(
            recipient_email=str(request.recipient.email),
            recipient_name=request.recipient.name,
            first_name=request.first_name,
            reset_token=request.reset_token,
            reset_url=(
                str(request.reset_url)
                if request.reset_url
                else None
            ),
            expires_in_minutes=request.expires_in_minutes,
            external_reference=request.external_reference,
            priority=request.priority,
        )

        await service.db.commit()

        task = send_notification.apply_async(
            args=[str(notification.id)],
            task_id=f"notification-{notification.id}",
        )

        return NotificationQueuedResponse(
            notification_id=notification.id,
            status=notification.status,
            provider=notification.provider,
            task_id=task.id,
            message="Password-reset email queued successfully",
        )

    except EmailServiceError as exc:
        await service.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception:
        await service.db.rollback()
        raise


@router.post(
    "/email/password-changed",
    response_model=NotificationQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_key)],
)
async def queue_password_changed_email(
    request: PasswordChangedEmailRequest,
    service: EmailService = Depends(get_email_service),
) -> NotificationQueuedResponse:
    """
    Queue a password-changed security alert.
    """

    try:
        notification = await service.create_password_changed_email(
            recipient_email=str(request.recipient.email),
            recipient_name=request.recipient.name,
            first_name=request.first_name,
            changed_at=request.changed_at,
            ip_address=request.ip_address,
            user_agent=request.user_agent,
            external_reference=request.external_reference,
            priority=request.priority,
        )

        await service.db.commit()

        task = send_notification.apply_async(
            args=[str(notification.id)],
            task_id=f"notification-{notification.id}",
        )

        return NotificationQueuedResponse(
            notification_id=notification.id,
            status=notification.status,
            provider=notification.provider,
            task_id=task.id,
            message="Password-changed email queued successfully",
        )

    except EmailServiceError as exc:
        await service.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception:
        await service.db.rollback()
        raise


@router.post(
    "/email/template",
    response_model=NotificationQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_key)],
)
async def queue_templated_email(
    request: TemplatedEmailRequest,
    service: EmailService = Depends(get_email_service),
) -> NotificationQueuedResponse:
    """
    Queue a registered Jinja2 email template.
    """

    try:
        notification = await service.create_templated_notification(
            recipient_email=str(request.recipient.email),
            recipient_name=request.recipient.name,
            template_name=request.template_name,
            template_data=request.template_data,
            subject=request.subject,
            sender_email=(
                str(request.sender.email)
                if request.sender
                else None
            ),
            sender_name=(
                request.sender.name
                if request.sender
                else None
            ),
            reply_to_email=(
                str(request.reply_to_email)
                if request.reply_to_email
                else None
            ),
            priority=request.priority,
            external_reference=request.external_reference,
            max_retry_count=request.max_retry_count,
            scheduled_at=request.scheduled_at,
            headers=request.headers,
            metadata=request.metadata,
        )

        await service.db.commit()

        task_options: dict[str, object] = {
            "args": [str(notification.id)],
            "task_id": f"notification-{notification.id}",
        }

        if request.scheduled_at:
            task_options["eta"] = request.scheduled_at

        task = send_notification.apply_async(**task_options)

        return NotificationQueuedResponse(
            notification_id=notification.id,
            status=notification.status,
            provider=notification.provider,
            task_id=task.id,
            message="Templated email queued successfully",
        )

    except EmailServiceError as exc:
        await service.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception:
        await service.db.rollback()
        raise


@router.post(
    "/email/direct",
    response_model=NotificationQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_key)],
)
async def queue_direct_email(
    request: DirectEmailRequest,
    service: EmailService = Depends(get_email_service),
) -> NotificationQueuedResponse:
    """
    Queue an email without using a registered template.
    """

    try:
        notification = await service.create_direct_notification(
            recipient_email=str(request.recipient.email),
            recipient_name=request.recipient.name,
            subject=request.subject,
            body_text=request.body_text,
            body_html=request.body_html,
            sender_email=(
                str(request.sender.email)
                if request.sender
                else None
            ),
            sender_name=(
                request.sender.name
                if request.sender
                else None
            ),
            reply_to_email=(
                str(request.reply_to_email)
                if request.reply_to_email
                else None
            ),
            priority=request.priority,
            external_reference=request.external_reference,
            max_retry_count=request.max_retry_count,
            scheduled_at=request.scheduled_at,
            headers=request.headers,
            metadata=request.metadata,
        )

        await service.db.commit()

        task_options: dict[str, object] = {
            "args": [str(notification.id)],
            "task_id": f"notification-{notification.id}",
        }

        if request.scheduled_at:
            task_options["eta"] = request.scheduled_at

        task = send_notification.apply_async(**task_options)

        return NotificationQueuedResponse(
            notification_id=notification.id,
            status=notification.status,
            provider=notification.provider,
            task_id=task.id,
            message="Direct email queued successfully",
        )

    except EmailServiceError as exc:
        await service.db.rollback()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except Exception:
        await service.db.rollback()
        raise


@router.get(
    "",
    response_model=NotificationListResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def list_notifications(
    status_filter: NotificationStatus | None = Query(
        default=None,
        alias="status",
    ),
    provider: ProviderType | None = Query(default=None),
    recipient: str | None = Query(
        default=None,
        min_length=3,
        max_length=320,
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    """
    List notifications with filtering and pagination.
    """

    conditions = [
        Notification.is_deleted.is_(False),
    ]

    if status_filter is not None:
        conditions.append(
            Notification.status == status_filter
        )

    if provider is not None:
        conditions.append(
            Notification.provider == provider
        )

    if recipient:
        conditions.append(
            Notification.recipient == recipient.strip()
        )

    count_statement = (
        select(func.count(Notification.id))
        .where(*conditions)
    )

    total_result = await db.execute(count_statement)
    total = int(total_result.scalar_one())

    offset = (page - 1) * page_size

    statement = (
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(statement)
    notifications = list(result.scalars().all())

    total_pages = (
        (total + page_size - 1) // page_size
        if total
        else 0
    )

    return NotificationListResponse(
        items=[
            NotificationSummaryResponse.model_validate(
                notification
            )
            for notification in notifications
        ],
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=total_pages,
        ),
    )

@router.get(
    "/operations/summary",
    response_model=dict[str, int],
    dependencies=[Depends(require_internal_api_key)],
)
async def get_notification_summary(
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """
    Return operational notification counts grouped by status.
    """

    statement = (
        select(
            Notification.status,
            func.count(Notification.id),
        )
        .where(Notification.is_deleted.is_(False))
        .group_by(Notification.status)
    )

    result = await db.execute(statement)

    summary = {
        notification_status.value: 0
        for notification_status in NotificationStatus
    }

    for notification_status, count in result.all():
        summary[notification_status.value] = int(count)

    summary["TOTAL"] = sum(summary.values())

    return summary


@router.get(
    "/operations/ready",
    response_model=MessageResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def notification_operations_ready(
    service: EmailService = Depends(get_email_service),
) -> MessageResponse:
    """
    Check whether the configured email provider is available.
    """

    provider_healthy = service.provider.health_check()

    if not provider_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Email provider "
                f"'{service.provider.provider_type.value}' "
                "is unavailable"
            ),
        )

    return MessageResponse(
        message=(
            f"Email provider "
            f"'{service.provider.provider_type.value}' "
            "is ready"
        ),
    )

@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def get_notification(
    notification_id: UUID,
    service: EmailService = Depends(get_email_service),
) -> NotificationResponse:
    """
    Return one notification and its delivery attempts.
    """

    try:
        notification = await service.get_notification(
            notification_id,
            include_attempts=True,
        )

        return NotificationResponse.model_validate(
            notification
        )

    except NotificationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{notification_id}/retry",
    response_model=NotificationQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_api_key)],
)
async def retry_failed_notification(
    notification_id: UUID,
    request: RetryNotificationRequest,
    service: EmailService = Depends(get_email_service),
) -> NotificationQueuedResponse:
    """
    Queue an explicit retry for a failed notification.
    """

    try:
        notification = await service.retry_notification(
            notification_id,
            reset_retry_count=request.reset_retry_count,
        )

        countdown = request.delay_seconds or 0

        task = retry_notification.apply_async(
            args=[str(notification.id)],
            countdown=countdown,
            task_id=f"notification-retry-{notification.id}",
        )

        return NotificationQueuedResponse(
            notification_id=notification.id,
            status=notification.status,
            provider=notification.provider,
            task_id=task.id,
            message="Notification retry queued successfully",
        )

    except NotificationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except NotificationStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{notification_id}/cancel",
    response_model=NotificationResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def cancel_notification(
    notification_id: UUID,
    request: CancelNotificationRequest,
    service: EmailService = Depends(get_email_service),
) -> NotificationResponse:
    """
    Cancel a pending, failed, or retrying notification.
    """

    try:
        notification = await service.cancel_notification(
            notification_id
        )

        if request.reason:
            notification.error_message = (
                f"Cancelled: {request.reason}"
            )

            await service.db.commit()

            notification = await service.get_notification(
                notification.id,
                include_attempts=True,
            )

        return NotificationResponse.model_validate(
            notification
        )

    except NotificationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except NotificationStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/{notification_id}/send-now",
    response_model=NotificationResponse,
    dependencies=[Depends(require_internal_api_key)],
)
async def send_notification_immediately(
    notification_id: UUID,
    service: EmailService = Depends(get_email_service),
) -> NotificationResponse:
    """
    Deliver a notification synchronously.

    This endpoint is mainly useful for development, support operations, and
    controlled administrative workflows. Normal production requests should
    use the asynchronous queue endpoints.
    """

    try:
        notification = await service.send_notification(
            notification_id
        )

        return NotificationResponse.model_validate(
            notification
        )

    except NotificationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except NotificationStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if exc.retryable
                else status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail={
                "message": str(exc),
                "retryable": exc.retryable,
                "response_code": exc.response_code,
            },
        ) from exc


