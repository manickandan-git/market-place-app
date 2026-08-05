from __future__ import annotations

import pytest

from integration_tests.catalog import create_stocked_product
from integration_tests.helpers import get_clean_cart, unique

pytestmark = pytest.mark.integration


async def test_cart_add_update_readiness_remove(
    clients,
    buyer,
    seller_a,
    admin,
    inventory_sync,
):
    _, variant, _ = await create_stocked_product(
        clients,
        admin_token=admin.token,
        seller_token=seller_a.token,
        inventory_sync_token=inventory_sync.token,
    )

    cart = await get_clean_cart(clients, buyer.token)
    assert cart["items"] == []

    added = await clients.cart.json(
        "POST",
        "/api/v1/cart/items",
        token=buyer.token,
        headers={
            "If-Match-Version": str(cart["version"]),
            "Idempotency-Key": unique("cart-add"),
        },
        json={
            "product_id": variant["product_id"],
            "variant_id": variant["id"],
            "quantity": 2,
        },
        expected=201,
    )
    assert len(added["items"]) == 1
    item = added["items"][0]
    assert item["sku"] == variant["sku"]
    assert item["quantity"] == 2
    assert float(item["unit_price"]) == float(variant["price_amount"])

    updated = await clients.cart.json(
        "PATCH",
        f"/api/v1/cart/items/{item['id']}",
        token=buyer.token,
        headers={"If-Match-Version": str(added["version"])},
        json={"quantity": 3},
        expected=200,
    )
    assert updated["items"][0]["quantity"] == 3

    readiness = await clients.cart.json(
        "POST",
        "/api/v1/cart/readiness",
        token=buyer.token,
        headers={"If-Match-Version": str(updated["version"])},
        expected=200,
    )
    assert readiness["ready"] is True
    assert readiness["price_changed"] is False

    cleared = await clients.cart.json(
        "DELETE",
        f"/api/v1/cart/items/{item['id']}",
        token=buyer.token,
        headers={"If-Match-Version": str(updated["version"])},
        expected=200,
    )
    assert cleared["items"] == []


async def test_cart_add_item_is_idempotent(
    clients,
    buyer,
    seller_a,
    admin,
    inventory_sync,
):
    _, variant, _ = await create_stocked_product(
        clients,
        admin_token=admin.token,
        seller_token=seller_a.token,
        inventory_sync_token=inventory_sync.token,
    )
    cart = await get_clean_cart(clients, buyer.token)
    key = unique("cart-add-idempotent")
    body = {
        "product_id": variant["product_id"],
        "variant_id": variant["id"],
        "quantity": 1,
    }

    first = await clients.cart.json(
        "POST",
        "/api/v1/cart/items",
        token=buyer.token,
        headers={"If-Match-Version": str(cart["version"]), "Idempotency-Key": key},
        json=body,
        expected=201,
    )
    replay = await clients.cart.json(
        "POST",
        "/api/v1/cart/items",
        token=buyer.token,
        headers={"If-Match-Version": str(cart["version"]), "Idempotency-Key": key},
        json=body,
        expected=201,
    )
    assert len(replay["items"]) == len(first["items"]) == 1

    # Leave the cart clean for downstream (order/payment/shipping) tests.
    await get_clean_cart(clients, buyer.token)
