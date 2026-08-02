from app.dependencies.auth import get_current_principal, get_optional_principal
from app.main import app
from tests.conftest import BUYER_ID, add_payload


async def test_create_and_use_guest_cart(guest_context):
    client, _, _ = guest_context
    created = await client.post("/api/v1/guest-carts")
    assert created.status_code == 201
    token = created.json()["cart_token"]
    cart = created.json()["cart"]
    added = await client.post(
        "/api/v1/cart/items",
        json=add_payload(1),
        headers={
            "X-Cart-Token": token,
            "If-Match-Version": str(cart["version"]),
            "Idempotency-Key": "guest-add-key1",
        },
    )
    assert added.status_code == 201
    assert added.json()["customer_id"] is None


async def test_missing_guest_token_is_rejected(guest_context):
    client, _, _ = guest_context
    response = await client.get("/api/v1/cart")
    assert response.status_code == 401


async def test_guest_cart_merges_into_buyer(guest_context):
    client, _, _ = guest_context
    created = (await client.post("/api/v1/guest-carts")).json()
    token = created["cart_token"]
    guest = (
        await client.post(
            "/api/v1/cart/items",
            json=add_payload(2),
            headers={
                "X-Cart-Token": token,
                "If-Match-Version": str(created["cart"]["version"]),
                "Idempotency-Key": "guest-merge-add",
            },
        )
    ).json()
    assert guest["total_quantity"] == 2

    async def buyer():
        from app.dependencies.auth import Principal

        return Principal(
            subject=BUYER_ID,
            roles=frozenset({"buyer"}),
            scopes=frozenset(),
            claims={"sub": str(BUYER_ID)},
        )

    app.dependency_overrides[get_optional_principal] = buyer
    app.dependency_overrides[get_current_principal] = buyer
    merged = await client.post("/api/v1/cart/merge", json={"guest_cart_token": token})
    assert merged.status_code == 200
    assert merged.json()["customer_id"] == str(BUYER_ID)
    assert merged.json()["total_quantity"] == 2
