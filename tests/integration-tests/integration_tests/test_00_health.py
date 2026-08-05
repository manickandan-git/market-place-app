from __future__ import annotations

import pytest

from integration_tests.helpers import wait_until_healthy

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("base_attribute", "path_attribute"),
    [
        ("auth_service_url", "auth_health_path"),
        ("user_service_url", "user_health_path"),
        ("product_service_url", "product_health_path"),
        ("inventory_service_url", "inventory_health_path"),
        ("notification_service_url", "notification_health_path"),
        ("cart_service_url", "cart_health_path"),
        ("order_service_url", "order_health_path"),
        ("payment_service_url", "payment_health_path"),
        ("shipping_service_url", "shipping_health_path"),
    ],
)
async def test_service_is_healthy(settings, base_attribute, path_attribute):
    url = settings.url(
        getattr(settings, base_attribute),
        getattr(settings, path_attribute),
    )
    await wait_until_healthy(
        url,
        timeout_seconds=settings.startup_timeout_seconds,
        verify=settings.verify_tls,
    )


async def test_identity_publishes_jwks(clients, settings):
    response = await clients.auth.request(
        "GET",
        settings.auth_jwks_path,
        expected=200,
    )
    document = response.json()
    assert document.get("keys"), "JWKS must contain at least one signing key"
    assert all(key.get("kid") for key in document["keys"])

