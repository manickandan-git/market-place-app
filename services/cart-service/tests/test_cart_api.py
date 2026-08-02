from tests.conftest import add_payload


async def get_cart(client):
    response = await client.get("/api/v1/cart")
    assert response.status_code == 200
    return response.json()


async def add_item(client, version, quantity=2, key="add-item-0001"):
    return await client.post(
        "/api/v1/cart/items",
        json=add_payload(quantity),
        headers={"If-Match-Version": str(version), "Idempotency-Key": key},
    )


async def test_authenticated_buyer_gets_one_active_cart(client):
    first = await get_cart(client)
    second = await get_cart(client)
    assert first["id"] == second["id"]
    assert first["customer_id"] is not None
    assert first["version"] == 1


async def test_add_item_uses_product_snapshot(client):
    cart = await get_cart(client)
    response = await add_item(client, cart["version"])
    assert response.status_code == 201
    body = response.json()
    assert body["total_quantity"] == 2
    assert body["subtotal"] == "39.98"
    assert body["items"][0]["sku"] == "TEST-SKU-001"


async def test_add_same_variant_increments_quantity(client):
    cart = await get_cart(client)
    first = (await add_item(client, cart["version"], 2, "add-item-0002")).json()
    second = await add_item(client, first["version"], 3, "add-item-0003")
    assert second.status_code == 201
    assert second.json()["total_quantity"] == 5
    assert len(second.json()["items"]) == 1


async def test_idempotency_replay_does_not_duplicate(client):
    cart = await get_cart(client)
    first = await add_item(client, cart["version"], 2, "same-key-0001")
    replay = await add_item(client, cart["version"], 2, "same-key-0001")
    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["total_quantity"] == 2


async def test_stale_version_is_rejected(client):
    cart = await get_cart(client)
    await add_item(client, cart["version"], 1, "stale-key-001")
    response = await add_item(client, cart["version"], 1, "stale-key-002")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"


async def test_update_and_remove_item(client):
    cart = await get_cart(client)
    added = (await add_item(client, cart["version"], 1, "update-key-01")).json()
    item_id = added["items"][0]["id"]
    updated = await client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 4},
        headers={"If-Match-Version": str(added["version"])},
    )
    assert updated.json()["total_quantity"] == 4
    removed = await client.delete(
        f"/api/v1/cart/items/{item_id}",
        headers={"If-Match-Version": str(updated.json()["version"])},
    )
    assert removed.status_code == 200
    assert removed.json()["items"] == []


async def test_save_for_later_and_move_back(client):
    cart = await get_cart(client)
    added = (await add_item(client, cart["version"], 1, "save-key-0001")).json()
    item_id = added["items"][0]["id"]
    saved = await client.post(
        f"/api/v1/cart/items/{item_id}/save-for-later",
        headers={"If-Match-Version": str(added["version"])},
    )
    assert saved.status_code == 200
    assert len(saved.json()["saved_items"]) == 1
    saved_id = saved.json()["saved_items"][0]["id"]
    moved = await client.post(
        f"/api/v1/cart/saved-items/{saved_id}/move-to-cart",
        headers={"If-Match-Version": str(saved.json()["version"])},
    )
    assert moved.status_code == 200
    assert len(moved.json()["items"]) == 1
    assert moved.json()["saved_items"] == []


async def test_clear_cart(client):
    cart = await get_cart(client)
    added = (await add_item(client, cart["version"], 1, "clear-key-001")).json()
    response = await client.delete(
        "/api/v1/cart",
        headers={"If-Match-Version": str(added["version"])},
    )
    assert response.status_code == 200
    assert response.json()["subtotal"] == "0.00"
