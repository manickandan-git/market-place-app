async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_openapi_contains_cart_routes(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/cart/items" in response.json()["paths"]
