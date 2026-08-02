from __future__ import annotations

import pytest

from integration_tests.helpers import unique

pytestmark = [pytest.mark.integration, pytest.mark.notification]


def _require_configuration(settings) -> None:
    if not settings.notification_test_endpoint:
        pytest.skip(
            "Set NOTIFICATION_TEST_ENDPOINT to your internal notification route"
        )
    if not settings.internal_api_key:
        pytest.skip("Set INTERNAL_API_KEY for Notification Service contract tests")


def _payload() -> dict:
    return {
        "recipient_email": "integration-recipient@example.com",
        "template_name": "verification",
        "template_context": {
            "display_name": "Integration User",
            "verification_url": "https://example.test/verify/integration",
        },
        "idempotency_key": unique("notification"),
    }


async def test_notification_rejects_missing_and_wrong_internal_key(
    clients,
    settings,
):
    _require_configuration(settings)
    missing = await clients.notification.request(
        "POST",
        settings.notification_test_endpoint,
        json=_payload(),
    )
    assert missing.status_code in {401, 403}

    wrong = await clients.notification.request(
        "POST",
        settings.notification_test_endpoint,
        headers={settings.notification_api_key_header: "definitely-wrong"},
        json=_payload(),
    )
    assert wrong.status_code in {401, 403}


async def test_notification_accepts_internal_key(clients, settings):
    _require_configuration(settings)
    payload = _payload()
    response = await clients.notification.request(
        "POST",
        settings.notification_test_endpoint,
        headers={settings.notification_api_key_header: settings.internal_api_key},
        json=payload,
    )
    assert response.status_code in {200, 201, 202}, response.text

