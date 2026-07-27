from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.notification_client import NotificationClient

pytestmark = pytest.mark.real_notification_client


def _unreachable_client() -> NotificationClient:
    """
    A client pointed at a port nothing listens on, so every call fails fast
    with a real httpx connection error instead of a mocked one.
    """

    return NotificationClient(
        base_url="http://127.0.0.1:1",
        api_key="test-key",
        timeout_seconds=2.0,
    )


async def test_send_verification_email_does_not_raise_when_unreachable() -> (
    None
):
    client = _unreachable_client()

    await client.send_verification_email(
        recipient_email="buyer@example.com",
        recipient_name="Test Buyer",
        first_name="Test",
        verification_token="dummy-verification-token",
        expires_in_minutes=30,
    )


async def test_send_password_reset_email_does_not_raise_when_unreachable() -> (
    None
):
    client = _unreachable_client()

    await client.send_password_reset_email(
        recipient_email="buyer@example.com",
        recipient_name="Test Buyer",
        first_name="Test",
        reset_token="dummy-reset-token",
        expires_in_minutes=30,
    )


async def test_send_password_changed_email_does_not_raise_when_unreachable() -> (
    None
):
    client = _unreachable_client()

    await client.send_password_changed_email(
        recipient_email="buyer@example.com",
        recipient_name="Test Buyer",
        first_name="Test",
        changed_at=datetime.now(UTC),
    )
