from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from celery import Task
from celery.exceptions import MaxRetriesExceededError

from app.celery_app import celery_app
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.email_service import (
    EmailDeliveryError,
    EmailService,
    NotificationNotFoundError,
)

logger = logging.getLogger(__name__)

settings = get_settings()


class NotificationTask(Task):
    """
    Base Celery task.

    Adds automatic retry support and structured logging.

    retry_backoff is set to the configured base delay (rather than the bare
    `True` default of a 1-second base) so CELERY_RETRY_DELAY_SECONDS actually
    controls the exponential-backoff schedule. Call sites must not pass an
    explicit `countdown=` to `retry()`, since that bypasses retry_backoff/
    retry_jitter entirely and forces a flat delay on every attempt.
    """

    autoretry_for = ()

    retry_backoff = settings.celery_retry_delay_seconds
    retry_jitter = True
    retry_kwargs = {
        "max_retries": settings.celery_task_max_retries,
    }


@celery_app.task(
    bind=True,
    base=NotificationTask,
    name="app.tasks.send_notification",
)
def send_notification(
    self: NotificationTask,
    notification_id: str,
) -> dict:
    """
    Celery entrypoint.

    Sends one pending notification.

    This wrapper is synchronous because Celery executes normal
    Python callables. The business logic remains asynchronous.
    """

    return asyncio.run(
        _send_notification(
            task=self,
            notification_id=UUID(notification_id),
        )
    )


async def _send_notification(
    *,
    task: NotificationTask,
    notification_id: UUID,
) -> dict:
    async with AsyncSessionLocal() as db:

        service = EmailService(db)

        try:

            notification = await service.send_notification(
                notification_id
            )

            logger.info(
                "Notification sent successfully",
                extra={
                    "notification_id": str(notification.id),
                },
            )

            return {
                "notification_id": str(notification.id),
                "status": notification.status.value,
                "provider": notification.provider.value,
                "provider_message_id": notification.provider_message_id,
            }

        except NotificationNotFoundError:

            logger.error(
                "Notification not found",
                extra={
                    "notification_id": str(notification_id),
                },
            )

            raise

        except EmailDeliveryError as exc:

            logger.warning(
                "Notification delivery failed",
                extra={
                    "notification_id": str(notification_id),
                    "retryable": exc.retryable,
                },
            )

            if exc.retryable:

                try:
                    raise task.retry(exc=exc)

                except MaxRetriesExceededError:

                    logger.error(
                        "Maximum retries exceeded",
                        extra={
                            "notification_id": str(
                                notification_id
                            )
                        },
                    )

                    raise

            raise


@celery_app.task(
    bind=True,
    base=NotificationTask,
    name="app.tasks.retry_notification",
)
def retry_notification(
    self: NotificationTask,
    notification_id: str,
) -> dict:
    return asyncio.run(
        _retry_notification(
            task=self,
            notification_id=UUID(notification_id),
        )
    )


async def _retry_notification(
    *,
    task: NotificationTask,
    notification_id: UUID,
) -> dict:
    async with AsyncSessionLocal() as db:
        service = EmailService(db)

        try:
            notification = await service.send_notification(
                notification_id
            )

            return {
                "notification_id": str(notification.id),
                "status": notification.status.value,
                "provider": notification.provider.value,
                "provider_message_id": (
                    notification.provider_message_id
                ),
            }

        except EmailDeliveryError as exc:
            if exc.retryable:
                raise task.retry(exc=exc)

            raise

@celery_app.task(
    bind=True,
    base=NotificationTask,
    name="app.tasks.health_check",
)
def health_check(
    self: NotificationTask,
) -> dict:
    """
    Worker health check.
    """

    return {
        "status": "healthy",
        "worker": self.request.hostname,
    }