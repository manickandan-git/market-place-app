from __future__ import annotations

from uuid import uuid4

import pytest

from integration_tests.helpers import unique

pytestmark = pytest.mark.integration


async def _create_catalog(clients, admin_token: str, seller_token: str):
    suffix = uuid4().hex[:10]
    category = await clients.product.json(
        "POST",
        "/api/v1/admin/categories",
        token=admin_token,
        json={
            "name": f"Integration Category {suffix}",
            "slug": f"integration-category-{suffix}",
            "description": "Created by the Marketplace integration suite",
        },
        expected=201,
    )
    product = await clients.product.json(
        "POST",
        "/api/v1/seller/products",
        token=seller_token,
        headers={"Idempotency-Key": unique("create-product")},
        json={
            "category_id": category["id"],
            "name": f"Integration Phone {suffix}",
            "slug": f"integration-phone-{suffix}",
            "short_description": "Product/Inventory contract test",
            "brand": "Integration",
            "variants": [
                {
                    "sku": f"PHONE-{suffix.upper()}-BLK",
                    "name": "Black",
                    "price_amount": "499.99",
                    "currency_code": "USD",
                    "is_active": True,
                }
            ],
        },
        expected=201,
    )
    active = await clients.product.json(
        "PUT",
        f"/api/v1/seller/products/{product['id']}/status",
        token=seller_token,
        headers={"If-Match": str(product["version"])},
        json={"status": "active"},
        expected=200,
    )
    return active, active["variants"][0]


async def test_product_inventory_lifecycle(
    clients,
    admin,
    seller_a,
    buyer,
    inventory_sync,
):
    product, variant = await _create_catalog(
        clients,
        admin.token,
        seller_a.token,
    )
    assert product["owner_user_id"] == seller_a.subject

    sync_payload = {
        "product_id": product["id"],
        "variant_id": variant["id"],
        "seller_id": product["owner_user_id"],
        "sku": variant["sku"],
        "is_active": True,
    }
    projection = await clients.inventory.json(
        "PUT",
        f"/api/v1/internal/catalog-skus/{variant['id']}",
        token=inventory_sync.token,
        json=sync_payload,
        expected=200,
    )
    assert projection["sku"] == variant["sku"]

    # Replaying the same event must not create a duplicate projection.
    replay = await clients.inventory.json(
        "PUT",
        f"/api/v1/internal/catalog-skus/{variant['id']}",
        token=inventory_sync.token,
        json=sync_payload,
        expected=200,
    )
    assert replay["variant_id"] == projection["variant_id"]

    warehouse = await clients.inventory.json(
        "POST",
        "/api/v1/admin/warehouses",
        token=admin.token,
        json={
            "code": unique("WH").upper(),
            "name": "Integration Warehouse",
            "address_reference": "integration-address",
        },
        expected=201,
    )
    item = await clients.inventory.json(
        "POST",
        "/api/v1/seller/inventory",
        token=seller_a.token,
        headers={"Idempotency-Key": unique("create-stock")},
        json={
            "warehouse_id": warehouse["id"],
            "product_id": product["id"],
            "variant_id": variant["id"],
            "sku": variant["sku"],
            "initial_quantity": 100,
            "low_stock_threshold": 5,
        },
        expected=201,
    )
    assert (item["on_hand_quantity"], item["reserved_quantity"]) == (100, 0)

    availability = await clients.inventory.json(
        "GET",
        f"/api/v1/availability/{variant['sku']}",
        expected=200,
    )
    assert availability["available_quantity"] == 100

    first = await clients.inventory.json(
        "POST",
        "/api/v1/reservations",
        token=buyer.token,
        headers={"Idempotency-Key": unique("reserve-release")},
        json={
            "inventory_item_id": item["id"],
            "quantity": 5,
            "cart_reference": unique("cart"),
        },
        expected=201,
    )
    after_reserve = await clients.inventory.json(
        "GET",
        f"/api/v1/seller/inventory/{item['id']}",
        token=seller_a.token,
        expected=200,
    )
    assert after_reserve["on_hand_quantity"] == 100
    assert after_reserve["reserved_quantity"] == 5
    assert after_reserve["available_quantity"] == 95

    await clients.inventory.json(
        "POST",
        f"/api/v1/reservations/{first['id']}/release",
        token=buyer.token,
        json={"reason": "customer_cancelled", "note": "integration test"},
        expected=200,
    )
    after_release = await clients.inventory.json(
        "GET",
        f"/api/v1/seller/inventory/{item['id']}",
        token=seller_a.token,
        expected=200,
    )
    assert after_release["available_quantity"] == 100

    second = await clients.inventory.json(
        "POST",
        "/api/v1/reservations",
        token=buyer.token,
        headers={"Idempotency-Key": unique("reserve-commit")},
        json={"inventory_item_id": item["id"], "quantity": 5},
        expected=201,
    )
    await clients.inventory.json(
        "POST",
        f"/api/v1/reservations/{second['id']}/commit",
        token=buyer.token,
        json={"order_reference": unique("order")},
        expected=200,
    )
    final_item = await clients.inventory.json(
        "GET",
        f"/api/v1/seller/inventory/{item['id']}",
        token=seller_a.token,
        expected=200,
    )
    assert final_item["on_hand_quantity"] == 95
    assert final_item["reserved_quantity"] == 0
    assert final_item["available_quantity"] == 95

    oversell = await clients.inventory.request(
        "POST",
        "/api/v1/reservations",
        token=buyer.token,
        headers={"Idempotency-Key": unique("oversell")},
        json={"inventory_item_id": item["id"], "quantity": 96},
    )
    assert 400 <= oversell.status_code < 500, oversell.text
    unchanged = await clients.inventory.json(
        "GET",
        f"/api/v1/seller/inventory/{item['id']}",
        token=seller_a.token,
        expected=200,
    )
    assert unchanged["available_quantity"] == 95

    public_product = await clients.product.json(
        "GET",
        f"/api/v1/products/{product['id']}",
        expected=200,
    )
    assert public_product["id"] == product["id"]

