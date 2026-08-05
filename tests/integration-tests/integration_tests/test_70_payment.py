from __future__ import annotations

from decimal import Decimal

import pytest

from integration_tests.catalog import create_stocked_product
from integration_tests.helpers import unique
from integration_tests.order_flow import checkout_new_order
from integration_tests.stripe_webhook import (
    build_payment_intent_event,
    sign_stripe_payload,
)

pytestmark = pytest.mark.integration


async def _post_webhook(
    clients, settings, event_type: str, payment_intent_id: str, **kw
):
    payload = build_payment_intent_event(event_type, payment_intent_id, **kw)
    signature = sign_stripe_payload(settings.stripe_webhook_secret, payload)
    return await clients.payment.request(
        "POST",
        "/api/v1/webhooks/stripe",
        content=payload,
        headers={
            "Stripe-Signature": signature,
            "Content-Type": "application/json",
        },
        expected=200,
    )


async def _get_order(clients, buyer, order_id: str) -> dict:
    return await clients.order.json(
        "GET", f"/api/v1/orders/{order_id}", token=buyer.token, expected=200
    )


async def test_payment_authorized_then_partial_and_full_refund(
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
    order = await checkout_new_order(clients, buyer, variant, quantity=2)
    assert order["status"] == "pending_payment"

    created = await clients.payment.json(
        "POST",
        "/api/v1/payments",
        token=buyer.token,
        headers={"Idempotency-Key": unique("payment-create")},
        json={"order_id": order["id"]},
        expected=201,
    )
    payment = created["payment"]
    assert payment["status"] == "pending"
    assert created["client_secret"]

    await _post_webhook(
        clients,
        settings,
        "payment_intent.succeeded",
        payment["provider_payment_intent_id"],
    )

    confirmed = await _get_order(clients, buyer, order["id"])
    assert confirmed["status"] == "confirmed"
    assert confirmed["payment_status"] == "authorized"

    total = Decimal(str(payment["amount"]))
    half = (total / 2).quantize(Decimal("0.01"))

    partial_refund = await clients.payment.json(
        "POST",
        f"/api/v1/payments/{payment['id']}/refund",
        token=buyer.token,
        json={"amount": str(half), "reason": "integration test partial refund"},
        expected=201,
    )
    assert partial_refund["status"] == "succeeded"

    after_partial = await _get_order(clients, buyer, order["id"])
    assert after_partial["payment_status"] == "partially_refunded"
    assert after_partial["status"] == "confirmed"

    final_refund = await clients.payment.json(
        "POST",
        f"/api/v1/payments/{payment['id']}/refund",
        token=buyer.token,
        json={"reason": "integration test remainder refund"},
        expected=201,
    )
    assert final_refund["status"] == "succeeded"

    after_full = await _get_order(clients, buyer, order["id"])
    assert after_full["payment_status"] == "refunded"
    assert after_full["status"] == "confirmed"


async def test_payment_failed_releases_stock(
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
        quantity=20,
    )
    order = await checkout_new_order(clients, buyer, variant, quantity=3)
    assert order["status"] == "pending_payment"

    availability_during_hold = await clients.inventory.json(
        "GET", f"/api/v1/availability/{variant['sku']}", expected=200
    )
    assert availability_during_hold["available_quantity"] == 17

    created = await clients.payment.json(
        "POST",
        "/api/v1/payments",
        token=buyer.token,
        headers={"Idempotency-Key": unique("payment-create")},
        json={"order_id": order["id"]},
        expected=201,
    )
    payment = created["payment"]

    await _post_webhook(
        clients,
        settings,
        "payment_intent.payment_failed",
        payment["provider_payment_intent_id"],
        decline_message="Your card was declined.",
    )

    failed = await _get_order(clients, buyer, order["id"])
    assert failed["status"] == "payment_failed"

    availability_after_release = await clients.inventory.json(
        "GET", f"/api/v1/availability/{variant['sku']}", expected=200
    )
    assert availability_after_release["available_quantity"] == 20
