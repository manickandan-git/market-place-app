from __future__ import annotations

import logging

from celery import Celery
from celery.signals import (
    after_setup_logger,
    after_setup_task_logger,
    worker_process_init,
    worker_process_shutdown,
)

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "notification_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks",
    ],
)

celery_app.conf.update(
    task_default_queue="notifications",
    task_default_exchange="notifications",
    task_default_exchange_type="direct",
    task_default_routing_key="notifications",
    task_routes={
        "app.tasks.send_notification": {
            "queue": "notifications",
            "routing_key": "notifications",
        },
        "app.tasks.retry_notification": {
            "queue": "notification-retries",
            "routing_key": "notification-retries",
        },
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_accept_content=["json"],
    enable_utc=True,
    timezone="UTC",
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=500,
    task_send_sent_event=True,
    worker_send_task_events=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=None,
    task_time_limit=settings.celery_task_time_limit_seconds,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    task_default_retry_delay=settings.celery_default_retry_delay_seconds,
    task_annotations={
        "app.tasks.send_notification": {
            "rate_limit": settings.celery_email_rate_limit,
        },
        "app.tasks.retry_notification": {
            "rate_limit": settings.celery_email_rate_limit,
        },
    },
)

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """
    Configure logging for Celery workers and task loggers.
    """

    logging.basicConfig(
        level=getattr(
            logging,
            settings.log_level.upper(),
            logging.INFO,
        ),
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(processName)s | %(name)s | %(message)s"
        ),
    )


@after_setup_logger.connect
def setup_celery_logger(
    logger: logging.Logger,
    *args: object,
    **kwargs: object,
) -> None:
    """
    Configure the main Celery worker logger.
    """

    logger.setLevel(
        getattr(
            logging,
            settings.log_level.upper(),
            logging.INFO,
        )
    )


@after_setup_task_logger.connect
def setup_task_logger(
    logger: logging.Logger,
    *args: object,
    **kwargs: object,
) -> None:
    """
    Configure task-specific loggers.
    """

    logger.setLevel(
        getattr(
            logging,
            settings.log_level.upper(),
            logging.INFO,
        )
    )


@worker_process_init.connect
def on_worker_process_init(
    *args: object,
    **kwargs: object,
) -> None:
    """
    Run when each Celery worker child process starts.

    SQLAlchemy async engines should not reuse pooled database connections
    created in a parent process. Database connections are therefore created
    lazily inside each worker process.
    """

    logger.info(
        "Notification worker process initialized"
    )


@worker_process_shutdown.connect
def on_worker_process_shutdown(
    *args: object,
    **kwargs: object,
) -> None:
    """
    Dispose database connections when a worker process shuts down.

    Celery signal handlers are synchronous, so async cleanup is handled by
    the task execution layer. This signal is retained for lifecycle logging.
    """

    logger.info(
        "Notification worker process shutting down"
    )


configure_logging()