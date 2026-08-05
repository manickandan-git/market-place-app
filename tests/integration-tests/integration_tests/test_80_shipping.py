from __future__ import annotations

import pytest

from integration_tests.catalog import create_stocked_product
from integration_tests.helpers import unique
from integration_tests.order_flow import checkout_and_confirm

pytestmark = pytest.mark.integration


async def _get_order(clients, buyer, order_id: str) -> dict:
    return await clients.order.json(
        "GET", f"/api/v1/orders/{order_id}", token=buyer.token, expected=200
    )


async def test_shipment_lifecycle_drives_order_fulfillment(
    clients,
    settings,
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
    )
    order = await checkout_and_confirm(clients, settings, buyer, variant)
    assert order["status"] == "confirmed"

    shipment = await clients.shipping.json(
        "POST",
        "/api/v1/shipments",
        token=seller_a.token,
        headers={"Idempotency-Key": unique("shipment-create")},
        json={"order_id": order["id"], "carrier": "UPS"},
        expected=201,
    )
    assert shipment["status"] == "pending"
    assert shipment["seller_id"] == seller_a.subject
    processing_order = await _get_order(clients, buyer, order["id"])
    assert processing_order["status"] == "processing"

    tracking_number = unique("1Z")
    shipped = await clients.shipping.json(
        "POST",
        f"/api/v1/shipments/{shipment['id']}/ship",
        token=seller_a.token,
        json={"tracking_number": tracking_number},
        expected=200,
    )
    assert shipped["status"] == "shipped"
    assert shipped["tracking_number"] == tracking_number
    shipped_order = await _get_order(clients, buyer, order["id"])
    assert shipped_order["status"] == "shipped"

    delivered = await clients.shipping.json(
        "POST",
        f"/api/v1/shipments/{shipment['id']}/deliver",
        token=seller_a.token,
        json={},
        expected=200,
    )
    assert delivered["status"] == "delivered"
    assert len(delivered["events"]) == 3
    delivered_order = await _get_order(clients, buyer, order["id"])
    assert delivered_order["status"] == "delivered"

    by_order = await clients.shipping.json(
        "GET",
        f"/api/v1/shipments/by-order/{order['id']}",
        token=seller_a.token,
        expected=200,
    )
    assert by_order["id"] == shipment["id"]


async def test_shipment_exception_does_not_call_order(
    clients,
    settings,
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
    )
    order = await checkout_and_confirm(clients, settings, buyer, variant)

    shipment = await clients.shipping.json(
        "POST",
        "/api/v1/shipments",
        token=seller_a.token,
        headers={"Idempotency-Key": unique("shipment-exception")},
        json={"order_id": order["id"], "carrier": "FedEx"},
        expected=201,
    )
    processing_order = await _get_order(clients, buyer, order["id"])
    assert processing_order["status"] == "processing"

    failed = await clients.shipping.json(
        "POST",
        f"/api/v1/shipments/{shipment['id']}/exception",
        token=seller_a.token,
        json={"reason": "Lost in transit"},
        expected=200,
    )
    assert failed["status"] == "failed"
    assert failed["failure_reason"] == "Lost in transit"

    # No Order callback for a shipping exception (Order's fulfillment
    # machine only moves forward) — status must be unchanged.
    unchanged_order = await _get_order(clients, buyer, order["id"])
    assert unchanged_order["status"] == "processing"
