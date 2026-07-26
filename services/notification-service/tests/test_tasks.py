from __future__ import annotations

import inspect

from app.config import get_settings
from app.tasks import NotificationTask, _retry_notification, _send_notification


def test_notification_task_retry_backoff_uses_configured_delay() -> None:
    """
    retry_backoff must come from CELERY_RETRY_DELAY_SECONDS, not the bare
    `True` default (which uses an unconfigurable 1-second backoff base).
    """

    settings = get_settings()

    assert NotificationTask.retry_backoff == (
        settings.celery_retry_delay_seconds
    )
    assert NotificationTask.retry_backoff is not True


def test_notification_task_max_retries_uses_configured_value() -> None:
    settings = get_settings()

    assert NotificationTask.retry_kwargs == {
        "max_retries": settings.celery_task_max_retries,
    }


def test_retry_call_sites_do_not_hardcode_countdown() -> None:
    """
    A hardcoded `countdown=` on task.retry() bypasses retry_backoff and
    retry_jitter entirely, forcing a flat delay regardless of configuration.
    """

    for func in (_send_notification, _retry_notification):
        source = inspect.getsource(func)

        assert "countdown" not in source, (
            f"{func.__name__} must not pass an explicit countdown to "
            "task.retry(); that bypasses retry_backoff/retry_jitter."
        )
