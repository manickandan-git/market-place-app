from __future__ import annotations

import pytest

from integration_tests.catalog import create_stocked_product
from integration_tests.helpers import unique
from integration_tests.order_flow import SHIPPING_ADDRESS, add_to_cart, checkout

pytestmark = pytest.mark.integration


async def _available(clients, sku: str) -> int:
    availability = await clients.inventory.json(
        "GET", f"/api/v1/availability/{sku}", expected=200
    )
    return availability["available_quantity"]


async def test_checkout_reserves_stock_and_is_idempotent(
    clients,
    buyer,
    seller_a,
    admin,
    inventory_sync,
    checkout_retires_cart,
):
    _, variant, _ = await create_stocked_product(
        clients,
        admin_token=admin.token,
        seller_token=seller_a.token,
        inventory_sync_token=inventory_sync.token,
        quantity=50,
    )
    assert await _available(clients, variant["sku"]) == 50

    cart = await add_to_cart(clients, buyer, variant, quantity=2)
    idempotency_key = unique("checkout")
    order = await checkout(clients, buyer, cart, idempotency_key)

    assert order["status"] == "pending_payment"
    assert order["payment_status"] == "pending"
    assert float(order["grand_total"]) == 2 * float(cart["items"][0]["unit_price"])
    assert await _available(clients, variant["sku"]) == 48

    # Idempotency: replaying the same key returns the same order, without
    # reserving stock a second time.
    replay = await checkout(clients, buyer, cart, idempotency_key)
    assert replay["id"] == order["id"]
    assert await _available(clients, variant["sku"]) == 48

    # A second, genuinely new checkout attempt on the same (now
    # checked-out) cart must be rejected cleanly rather than raising the
    # unhandled 500 this session's fix addressed (uq_order_customer_cart).
    duplicate = await clients.order.request(
        "POST",
        "/api/v1/orders",
        token=buyer.token,
        headers={"Idempotency-Key": unique("checkout-duplicate")},
        json={
            "cart_id": cart["id"],
            "cart_version": cart["version"],
            "shipping_address": SHIPPING_ADDRESS,
        },
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "order_already_exists"


async def test_cancel_releases_reserved_stock(
    clients,
    buyer,
    seller_a,
    admin,
    inventory_sync,
    checkout_retires_cart,
):
    _, variant, _ = await create_stocked_product(
        clients,
        admin_token=admin.token,
        seller_token=seller_a.token,
        inventory_sync_token=inventory_sync.token,
        quantity=30,
    )
    cart = await add_to_cart(clients, buyer, variant, quantity=4)
    order = await checkout(clients, buyer, cart, unique("checkout"))
    assert order["status"] == "pending_payment"
    assert await _available(clients, variant["sku"]) == 26

    cancelled = await clients.order.json(
        "POST",
        f"/api/v1/orders/{order['id']}/cancel",
        token=buyer.token,
        headers={"If-Match": str(order["version"])},
        json={"reason": "Integration test cancellation"},
        expected=200,
    )
    assert cancelled["status"] == "cancelled"
    assert await _available(clients, variant["sku"]) == 30
