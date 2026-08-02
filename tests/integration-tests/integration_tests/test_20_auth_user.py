from __future__ import annotations

import pytest

from integration_tests.helpers import unique

pytestmark = pytest.mark.integration


async def test_auth_user_profile_boundary(clients, buyer):
    missing = await clients.user.request("GET", "/api/v1/me")
    assert missing.status_code == 401

    get_response = await clients.user.request(
        "GET",
        "/api/v1/me",
        token=buyer.token,
    )
    if get_response.status_code == 404:
        created = await clients.user.json(
            "POST",
            "/api/v1/me",
            token=buyer.token,
            json={
                "display_name": unique("Integration Buyer"),
                "first_name": "Integration",
                "last_name": "Buyer",
            },
            expected=201,
        )
    else:
        assert get_response.status_code == 200, get_response.text
        created = get_response.json()

    assert created["user_id"] == buyer.subject
    loaded = await clients.user.json(
        "GET",
        "/api/v1/me",
        token=buyer.token,
        expected=200,
    )
    assert loaded["user_id"] == buyer.subject


async def test_buyer_cannot_use_seller_product_endpoint(clients, buyer):
    response = await clients.product.request(
        "GET",
        "/api/v1/seller/products",
        token=buyer.token,
    )
    assert response.status_code == 403

