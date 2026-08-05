from __future__ import annotations

from typing import Any

from integration_tests.helpers import get_clean_cart, unique
from integration_tests.stripe_webhook import (
    build_payment_intent_event,
    sign_stripe_payload,
)

SHIPPING_ADDRESS = {
    "full_name": "Integration Buyer",
    "line1": "1 Market Street",
    "city": "Atlanta",
    "state_or_region": "GA",
    "postal_code": "30301",
    "country_code": "US",
}


async def add_to_cart(clients, buyer, variant: dict[str, Any], quantity: int) -> dict:
    cart = await get_clean_cart(clients, buyer.token)
    return await clients.cart.json(
        "POST",
        "/api/v1/cart/items",
        token=buyer.token,
        headers={
            "If-Match-Version": str(cart["version"]),
            "Idempotency-Key": unique("order-cart-add"),
        },
        json={
            "product_id": variant["product_id"],
            "variant_id": variant["id"],
            "quantity": quantity,
        },
        expected=201,
    )


async def checkout(
    clients, buyer, cart: dict[str, Any], idempotency_key: str | None = None
) -> dict:
    return await clients.order.json(
        "POST",
        "/api/v1/orders",
        token=buyer.token,
        headers={"Idempotency-Key": idempotency_key or unique("checkout")},
        json={
            "cart_id": cart["id"],
            "cart_version": cart["version"],
            "shipping_address": SHIPPING_ADDRESS,
        },
        expected=201,
    )


async def checkout_new_order(
    clients, buyer, variant: dict[str, Any], quantity: int = 2
) -> dict:
    """`add_to_cart` + `checkout` in one call, for tests that only need the
    resulting order and don't care about the cart itself."""
    cart = await add_to_cart(clients, buyer, variant, quantity)
    return await checkout(clients, buyer, cart)


async def checkout_and_confirm(
    clients, settings, buyer, variant: dict[str, Any], quantity: int = 2
) -> dict:
    """checkout_new_order + payment via a signed synthetic Stripe webhook,
    returning the order once it has reached `confirmed`. For tests (e.g.
    shipping) where payment mechanics aren't what's under test — see
    test_70_payment.py for the payment/refund flow itself."""
    order = await checkout_new_order(clients, buyer, variant, quantity)
    created = await clients.payment.json(
        "POST",
        "/api/v1/payments",
        token=buyer.token,
        headers={"Idempotency-Key": unique("payment-create")},
        json={"order_id": order["id"]},
        expected=201,
    )
    payment = created["payment"]
    payload = build_payment_intent_event(
        "payment_intent.succeeded", payment["provider_payment_intent_id"]
    )
    signature = sign_stripe_payload(settings.stripe_webhook_secret, payload)
    await clients.payment.request(
        "POST",
        "/api/v1/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
        expected=200,
    )
    return await clients.order.json(
        "GET", f"/api/v1/orders/{order['id']}", token=buyer.token, expected=200
    )
