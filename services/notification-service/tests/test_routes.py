
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Notification,
    NotificationStatus,
)


pytestmark = pytest.mark.asyncio


def mock_celery_result(
    task_id: str = "test-task-id",
) -> MagicMock:
    """
    Create a mock Celery AsyncResult returned by apply_async().
    """

    result = MagicMock()
    result.id = task_id
    return result


async def test_root_endpoint(
    client: AsyncClient,
) -> None:
    response = await client.get("/")

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "running"
    assert "service" in payload
    assert "version" in payload
    assert "environment" in payload
    assert payload["documentation"] == "/docs"


async def test_health_endpoint(
    client: AsyncClient,
) -> None:
    response = await client.get("/health")

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "healthy"
    assert "service" in payload
    assert "version" in payload
    assert "timestamp" in payload


async def test_protected_endpoint_requires_internal_api_key(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/notifications"
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid internal API key"
    )


async def test_protected_endpoint_rejects_invalid_api_key(
    client: AsyncClient,
    invalid_internal_api_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/notifications",
        headers=invalid_internal_api_headers,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Invalid internal API key"
    )


@patch("app.routes.send_notification.apply_async")
async def test_queue_verification_email(
    apply_async_mock: MagicMock,
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    verification_email_payload: dict[str, Any],
) -> None:
    apply_async_mock.return_value = mock_celery_result(
        "verification-task-123"
    )

    response = await client.post(
        "/api/v1/notifications/email/verification",
        headers=internal_api_headers,
        json=verification_email_payload,
    )

    assert response.status_code == 202

    payload = response.json()

    assert payload["notification_id"] is not None
    assert payload["status"] == NotificationStatus.PENDING.value
    assert payload["task_id"] == "verification-task-123"
    assert "verification" in payload["message"].lower()

    apply_async_mock.assert_called_once()

    call_kwargs = apply_async_mock.call_args.kwargs

    assert len(call_kwargs["args"]) == 1
    assert call_kwargs["task_id"].startswith(
        "notification-"
    )


@patch("app.routes.send_notification.apply_async")
async def test_queue_password_reset_email(
    apply_async_mock: MagicMock,
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    password_reset_email_payload: dict[str, Any],
) -> None:
    apply_async_mock.return_value = mock_celery_result(
        "password-reset-task-123"
    )

    response = await client.post(
        "/api/v1/notifications/email/password-reset",
        headers=internal_api_headers,
        json=password_reset_email_payload,
    )

    assert response.status_code == 202

    payload = response.json()

    assert payload["notification_id"] is not None
    assert payload["status"] == NotificationStatus.PENDING.value
    assert payload["task_id"] == "password-reset-task-123"
    assert "password" in payload["message"].lower()

    apply_async_mock.assert_called_once()


@patch("app.routes.send_notification.apply_async")
async def test_queue_password_changed_email(
    apply_async_mock: MagicMock,
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    password_changed_email_payload: dict[str, Any],
) -> None:
    apply_async_mock.return_value = mock_celery_result(
        "password-changed-task-123"
    )

    response = await client.post(
        "/api/v1/notifications/email/password-changed",
        headers=internal_api_headers,
        json=password_changed_email_payload,
    )

    assert response.status_code == 202

    payload = response.json()

    assert payload["notification_id"] is not None
    assert payload["status"] == NotificationStatus.PENDING.value
    assert payload["task_id"] == "password-changed-task-123"
    assert "password" in payload["message"].lower()

    apply_async_mock.assert_called_once()


@patch("app.routes.send_notification.apply_async")
async def test_queue_direct_email(
    apply_async_mock: MagicMock,
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    direct_email_payload: dict[str, Any],
) -> None:
    apply_async_mock.return_value = mock_celery_result(
        "direct-email-task-123"
    )

    response = await client.post(
        "/api/v1/notifications/email/direct",
        headers=internal_api_headers,
        json=direct_email_payload,
    )

    assert response.status_code == 202

    payload = response.json()

    assert payload["notification_id"] is not None
    assert payload["status"] == NotificationStatus.PENDING.value
    assert payload["task_id"] == "direct-email-task-123"
    assert "direct email" in payload["message"].lower()

    apply_async_mock.assert_called_once()

    call_kwargs = apply_async_mock.call_args.kwargs

    assert call_kwargs["task_id"].startswith(
        "notification-"
    )


@patch("app.routes.send_notification.apply_async")
async def test_queue_scheduled_direct_email_sets_eta(
    apply_async_mock: MagicMock,
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    direct_email_payload: dict[str, Any],
) -> None:
    apply_async_mock.return_value = mock_celery_result(
        "scheduled-email-task-123"
    )

    scheduled_payload = {
        **direct_email_payload,
        "scheduled_at": "2030-01-01T12:00:00+00:00",
    }

    response = await client.post(
        "/api/v1/notifications/email/direct",
        headers=internal_api_headers,
        json=scheduled_payload,
    )

    assert response.status_code == 202

    apply_async_mock.assert_called_once()

    call_kwargs = apply_async_mock.call_args.kwargs

    assert "eta" in call_kwargs
    assert call_kwargs["eta"] is not None


@patch("app.routes.send_notification.apply_async")
async def test_queue_templated_email(
    apply_async_mock: MagicMock,
    client: AsyncClient,
    internal_api_headers: dict[str, str],
) -> None:
    apply_async_mock.return_value = mock_celery_result(
        "templated-email-task-123"
    )

    payload = {
        "recipient": {
            "email": "customer@example.com",
            "name": "Marketplace Customer",
        },
        "template_name": "verification",
        "template_data": {
            "first_name": "Customer",
            "recipient_email": "customer@example.com",
            "verification_token": "token-123",
            "verification_url": (
                "http://localhost:3000/verify-email"
                "?token=token-123"
            ),
            "expires_in_minutes": 30,
            "company_name": "Marketplace",
            "support_email": "support@marketplace.local",
            "current_year": 2030,
        },
        "subject": "Verify your Marketplace account",
        "priority": "HIGH",
        "external_reference": "user-123",
        "max_retry_count": 3,
    }

    response = await client.post(
        "/api/v1/notifications/email/template",
        headers=internal_api_headers,
        json=payload,
    )

    assert response.status_code == 202

    response_payload = response.json()

    assert response_payload["notification_id"] is not None
    assert response_payload["status"] == (
        NotificationStatus.PENDING.value
    )
    assert response_payload["task_id"] == (
        "templated-email-task-123"
    )

    apply_async_mock.assert_called_once()


async def test_queue_direct_email_rejects_invalid_email(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    direct_email_payload: dict[str, Any],
) -> None:
    invalid_payload = {
        **direct_email_payload,
        "recipient": {
            "email": "not-an-email-address",
            "name": "Invalid Customer",
        },
    }

    response = await client.post(
        "/api/v1/notifications/email/direct",
        headers=internal_api_headers,
        json=invalid_payload,
    )

    assert response.status_code == 422


async def test_queue_direct_email_requires_body_content(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    direct_email_payload: dict[str, Any],
) -> None:
    invalid_payload = {
        **direct_email_payload,
        "body_text": None,
        "body_html": None,
    }

    response = await client.post(
        "/api/v1/notifications/email/direct",
        headers=internal_api_headers,
        json=invalid_payload,
    )

    assert response.status_code == 422


async def test_queue_verification_email_requires_token(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    verification_email_payload: dict[str, Any],
) -> None:
    invalid_payload = {
        key: value
        for key, value in verification_email_payload.items()
        if key != "verification_token"
    }

    response = await client.post(
        "/api/v1/notifications/email/verification",
        headers=internal_api_headers,
        json=invalid_payload,
    )

    assert response.status_code == 422


async def test_list_notifications(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
    failed_notification: Notification,
    sent_notification: Notification,
) -> None:
    response = await client.get(
        "/api/v1/notifications",
        headers=internal_api_headers,
    )

    assert response.status_code == 200

    payload = response.json()

    assert "items" in payload
    assert "pagination" in payload

    notification_ids = {
        item["id"]
        for item in payload["items"]
    }

    assert str(pending_notification.id) in notification_ids
    assert str(failed_notification.id) in notification_ids
    assert str(sent_notification.id) in notification_ids

    pagination = payload["pagination"]

    assert pagination["page"] == 1
    assert pagination["page_size"] == 25
    assert pagination["total_items"] >= 3


async def test_list_notifications_filtered_by_status(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
    failed_notification: Notification,
    sent_notification: Notification,
) -> None:
    response = await client.get(
        "/api/v1/notifications",
        headers=internal_api_headers,
        params={
            "status": NotificationStatus.FAILED.value,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["items"]

    assert all(
        item["status"] == NotificationStatus.FAILED.value
        for item in payload["items"]
    )

    notification_ids = {
        item["id"]
        for item in payload["items"]
    }

    assert str(failed_notification.id) in notification_ids
    assert str(pending_notification.id) not in notification_ids
    assert str(sent_notification.id) not in notification_ids


async def test_list_notifications_filtered_by_recipient(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
) -> None:
    response = await client.get(
        "/api/v1/notifications",
        headers=internal_api_headers,
        params={
            "recipient": pending_notification.recipient,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["items"]

    assert all(
        item["recipient"] == pending_notification.recipient
        for item in payload["items"]
    )


async def test_list_notifications_applies_pagination(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
    failed_notification: Notification,
    sent_notification: Notification,
) -> None:
    response = await client.get(
        "/api/v1/notifications",
        headers=internal_api_headers,
        params={
            "page": 1,
            "page_size": 2,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert len(payload["items"]) == 2
    assert payload["pagination"]["page"] == 1
    assert payload["pagination"]["page_size"] == 2
    assert payload["pagination"]["total_items"] >= 3
    assert payload["pagination"]["total_pages"] >= 2


async def test_list_notifications_rejects_invalid_page_size(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/notifications",
        headers=internal_api_headers,
        params={
            "page_size": 101,
        },
    )

    assert response.status_code == 422


async def test_get_notification(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
) -> None:
    response = await client.get(
        (
            "/api/v1/notifications/"
            f"{pending_notification.id}"
        ),
        headers=internal_api_headers,
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["id"] == str(pending_notification.id)
    assert payload["status"] == (
        NotificationStatus.PENDING.value
    )
    assert payload["subject"] == pending_notification.subject
    assert payload["recipient"] == (
        pending_notification.recipient
    )
    assert "attempts" in payload


async def test_get_notification_not_found(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
) -> None:
    notification_id = uuid4()

    response = await client.get(
        f"/api/v1/notifications/{notification_id}",
        headers=internal_api_headers,
    )

    assert response.status_code == 404


async def test_get_notification_rejects_invalid_uuid(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/notifications/not-a-valid-uuid",
        headers=internal_api_headers,
    )

    assert response.status_code == 422


@patch("app.routes.retry_notification.apply_async")
async def test_retry_failed_notification(
    apply_async_mock: MagicMock,
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    failed_notification: Notification,
) -> None:
    apply_async_mock.return_value = mock_celery_result(
        "retry-task-123"
    )

    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{failed_notification.id}/retry"
        ),
        headers=internal_api_headers,
        json={
            "delay_seconds": 15,
        },
    )

    assert response.status_code == 202

    payload = response.json()

    assert payload["notification_id"] == str(
        failed_notification.id
    )
    assert payload["task_id"] == "retry-task-123"
    assert "retry" in payload["message"].lower()

    apply_async_mock.assert_called_once()

    call_kwargs = apply_async_mock.call_args.kwargs

    assert call_kwargs["args"] == [
        str(failed_notification.id)
    ]
    assert call_kwargs["countdown"] == 15


@patch("app.routes.retry_notification.apply_async")
async def test_retry_failed_notification_without_delay(
    apply_async_mock: MagicMock,
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    failed_notification: Notification,
) -> None:
    apply_async_mock.return_value = mock_celery_result(
        "retry-task-no-delay"
    )

    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{failed_notification.id}/retry"
        ),
        headers=internal_api_headers,
        json={},
    )

    assert response.status_code == 202

    call_kwargs = apply_async_mock.call_args.kwargs

    assert call_kwargs["countdown"] == 0


async def test_retry_sent_notification_is_rejected(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    sent_notification: Notification,
) -> None:
    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{sent_notification.id}/retry"
        ),
        headers=internal_api_headers,
        json={
            "delay_seconds": 0,
        },
    )

    assert response.status_code == 409


async def test_retry_notification_not_found(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
) -> None:
    notification_id = uuid4()

    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{notification_id}/retry"
        ),
        headers=internal_api_headers,
        json={
            "delay_seconds": 0,
        },
    )

    assert response.status_code == 404


async def test_cancel_pending_notification(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
) -> None:
    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{pending_notification.id}/cancel"
        ),
        headers=internal_api_headers,
        json={
            "reason": "Customer requested cancellation",
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["id"] == str(pending_notification.id)
    assert payload["status"] == (
        NotificationStatus.CANCELLED.value
    )

    if "error_message" in payload:
        assert "Customer requested cancellation" in (
            payload["error_message"] or ""
        )


async def test_cancel_failed_notification(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    failed_notification: Notification,
) -> None:
    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{failed_notification.id}/cancel"
        ),
        headers=internal_api_headers,
        json={},
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == (
        NotificationStatus.CANCELLED.value
    )


async def test_cancel_sent_notification_is_rejected(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    sent_notification: Notification,
) -> None:
    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{sent_notification.id}/cancel"
        ),
        headers=internal_api_headers,
        json={
            "reason": "This should not be allowed",
        },
    )

    assert response.status_code == 409


async def test_cancel_notification_not_found(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
) -> None:
    notification_id = uuid4()

    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{notification_id}/cancel"
        ),
        headers=internal_api_headers,
        json={},
    )

    assert response.status_code == 404


async def test_send_notification_immediately(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
) -> None:
    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{pending_notification.id}/send-now"
        ),
        headers=internal_api_headers,
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["id"] == str(pending_notification.id)
    assert payload["status"] == (
        NotificationStatus.SENT.value
    )
    assert payload["provider_message_id"] is not None
    assert payload["sent_at"] is not None


async def test_send_already_sent_notification_is_rejected(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    sent_notification: Notification,
) -> None:
    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{sent_notification.id}/send-now"
        ),
        headers=internal_api_headers,
    )

    assert response.status_code == 409


async def test_send_notification_immediately_not_found(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
) -> None:
    notification_id = uuid4()

    response = await client.post(
        (
            "/api/v1/notifications/"
            f"{notification_id}/send-now"
        ),
        headers=internal_api_headers,
    )

    assert response.status_code == 404


async def test_notification_operations_summary(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
    failed_notification: Notification,
    sent_notification: Notification,
) -> None:
    response = await client.get(
        "/api/v1/notifications/operations/summary",
        headers=internal_api_headers,
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload[NotificationStatus.PENDING.value] >= 1
    assert payload[NotificationStatus.FAILED.value] >= 1
    assert payload[NotificationStatus.SENT.value] >= 1
    assert payload["TOTAL"] >= 3


async def test_notification_operations_ready(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/notifications/operations/ready",
        headers=internal_api_headers,
    )

    assert response.status_code == 200

    payload = response.json()

    assert "message" in payload
    assert "ready" in payload["message"].lower()


async def test_operations_paths_are_not_treated_as_uuid(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
) -> None:
    """
    Verify static operations routes are declared before /{notification_id}.
    """

    summary_response = await client.get(
        "/api/v1/notifications/operations/summary",
        headers=internal_api_headers,
    )

    ready_response = await client.get(
        "/api/v1/notifications/operations/ready",
        headers=internal_api_headers,
    )

    assert summary_response.status_code == 200
    assert ready_response.status_code == 200


async def test_list_notifications_excludes_soft_deleted_records(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
    db_session: AsyncSession,
) -> None:
    pending_notification.is_deleted = True
    await db_session.flush()

    response = await client.get(
        "/api/v1/notifications",
        headers=internal_api_headers,
    )

    assert response.status_code == 200

    payload = response.json()

    notification_ids = {
        item["id"]
        for item in payload["items"]
    }

    assert str(pending_notification.id) not in notification_ids


async def test_get_soft_deleted_notification_returns_not_found(
    client: AsyncClient,
    internal_api_headers: dict[str, str],
    pending_notification: Notification,
    db_session: AsyncSession,
) -> None:
    pending_notification.is_deleted = True
    await db_session.flush()

    response = await client.get(
        (
            "/api/v1/notifications/"
            f"{pending_notification.id}"
        ),
        headers=internal_api_headers,
    )

    assert response.status_code == 404
