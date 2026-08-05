from __future__ import annotations

from typing import Any
from uuid import uuid4

from integration_tests.clients import MarketplaceClients
from integration_tests.helpers import unique


async def create_stocked_product(
    clients: MarketplaceClients,
    *,
    admin_token: str,
    seller_token: str,
    inventory_sync_token: str,
    quantity: int = 50,
    unit_price: str = "29.99",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Category -> product -> variant -> publish -> sync to Inventory ->
    warehouse -> stock, in one call. Shared by the cart/order/payment/
    shipping workflow tests, which all need a real, purchasable SKU rather
    than re-deriving this setup independently (see test_30_product_inventory
    for the narrower, standalone version this generalizes).

    Returns (product, variant, inventory_item).
    """
    suffix = uuid4().hex[:10]
    category = await clients.product.json(
        "POST",
        "/api/v1/admin/categories",
        token=admin_token,
        json={
            "name": f"Checkout Category {suffix}",
            "slug": f"checkout-category-{suffix}",
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
            "name": f"Checkout Widget {suffix}",
            "slug": f"checkout-widget-{suffix}",
            "short_description": "Checkout workflow integration test product",
            "brand": "Integration",
            "variants": [
                {
                    "sku": f"WIDGET-{suffix.upper()}",
                    "name": "Default",
                    "price_amount": unit_price,
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
    variant = active["variants"][0]

    await clients.inventory.json(
        "PUT",
        f"/api/v1/internal/catalog-skus/{variant['id']}",
        token=inventory_sync_token,
        json={
            "product_id": active["id"],
            "variant_id": variant["id"],
            "seller_id": active["owner_user_id"],
            "sku": variant["sku"],
            "is_active": True,
        },
        expected=200,
    )
    warehouse = await clients.inventory.json(
        "POST",
        "/api/v1/admin/warehouses",
        token=admin_token,
        json={
            "code": unique("WH").upper(),
            "name": "Checkout Warehouse",
            "address_reference": "integration-address",
        },
        expected=201,
    )
    item = await clients.inventory.json(
        "POST",
        "/api/v1/seller/inventory",
        token=seller_token,
        headers={"Idempotency-Key": unique("create-stock")},
        json={
            "warehouse_id": warehouse["id"],
            "product_id": active["id"],
            "variant_id": variant["id"],
            "sku": variant["sku"],
            "initial_quantity": quantity,
            "low_stock_threshold": 5,
        },
        expected=201,
    )
    return active, variant, item
