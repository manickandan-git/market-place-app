from tests.conftest import add_payload


async def setup_item(client):
    cart = (await client.get("/api/v1/cart")).json()
    return (
        await client.post(
            "/api/v1/cart/items",
            json=add_payload(3),
            headers={
                "If-Match-Version": str(cart["version"]),
                "Idempotency-Key": "readiness-key-1",
            },
        )
    ).json()


async def test_cart_ready_when_inventory_is_available(test_context):
    client, _, inventory = test_context
    cart = await setup_item(client)
    inventory.available = 10
    response = await client.post(
        "/api/v1/cart/readiness",
        headers={"If-Match-Version": str(cart["version"])},
    )
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["items"][0]["available_quantity"] == 10


async def test_cart_not_ready_when_stock_is_insufficient(test_context):
    client, _, inventory = test_context
    cart = await setup_item(client)
    inventory.available = 1
    response = await client.post(
        "/api/v1/cart/readiness",
        headers={"If-Match-Version": str(cart["version"])},
    )
    assert response.json()["ready"] is False
    assert len(response.json()["unavailable_items"]) == 1


async def test_readiness_refreshes_changed_price(test_context):
    client, products, _ = test_context
    cart = await setup_item(client)
    products.price = products.price + 5
    products.version = 2
    response = await client.post(
        "/api/v1/cart/readiness",
        headers={"If-Match-Version": str(cart["version"])},
    )
    assert response.status_code == 200
    assert response.json()["price_changed"] is True
    refreshed = (await client.get("/api/v1/cart")).json()
    assert refreshed["items"][0]["unit_price"] == "24.99"
