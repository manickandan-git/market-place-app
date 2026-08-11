"""Tests for the add_to_cart tool."""

import pytest

from app.tools import add_to_cart
from app.tools.types import ToolContext


class FakeCartClient:
    def __init__(self, response=None):
        self.calls: list[tuple] = []
        self._response = response or {}

    async def add_item(
        self, access_token, product_id, variant_id, quantity, request_id
    ):
        self.calls.append((access_token, product_id, variant_id, quantity, request_id))
        return self._response


@pytest.fixture
def fake_cart_client(monkeypatch):
    client = FakeCartClient()
    monkeypatch.setattr(add_to_cart, "_client", client)
    return client


@pytest.mark.usefixtures("fake_cart_client")
async def test_add_to_cart(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "quantity": 2,
    }
    result = await add_to_cart.handle(args, context)
    assert result["authenticated"] is True
    assert result["cart"] == fake_cart_client._response
    assert fake_cart_client.calls == [("fake_token", "prod_1", "var_1", 2, "req_123")]


async def test_add_to_cart_requires_authentication(fake_cart_client):
    context = ToolContext(access_token=None, request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "quantity": 2,
    }
    result = await add_to_cart.handle(args, context)
    assert result["authenticated"] is False
    assert "message" in result
    assert fake_cart_client.calls == []


async def test_add_to_cart_invalid_quantity(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "quantity": 0,  # Invalid quantity
    }
    with pytest.raises(ValueError):
        await add_to_cart.handle(args, context)


async def test_add_to_cart_quantity_bound_enforced(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "quantity": 1001,  # Exceeds maximum allowed quantity
    }
    with pytest.raises(ValueError):
        await add_to_cart.handle(args, context)


async def test_add_to_cart_ignores_unexpected_args(fake_cart_client):
    # Pydantic v2 defaults extra="ignore", so unrecognized fields are
    # silently dropped rather than rejected.
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "quantity": 2,
        "unexpected_arg": "unexpected_value",
    }
    result = await add_to_cart.handle(args, context)
    assert result["authenticated"] is True
    assert result["cart"] == fake_cart_client._response
    assert fake_cart_client.calls == [("fake_token", "prod_1", "var_1", 2, "req_123")]


async def test_add_to_cart_with_missing_optional_args(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        # quantity is optional and should default to 1
    }
    result = await add_to_cart.handle(args, context)
    assert result["authenticated"] is True
    assert result["cart"] == fake_cart_client._response
    assert fake_cart_client.calls == [("fake_token", "prod_1", "var_1", 1, "req_123")]


async def test_add_to_cart_with_large_quantity(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "quantity": 1000,  # Maximum allowed quantity
    }
    result = await add_to_cart.handle(args, context)
    assert result["authenticated"] is True
    assert result["cart"] == fake_cart_client._response
    assert fake_cart_client.calls == [
        ("fake_token", "prod_1", "var_1", 1000, "req_123")
    ]


async def test_add_to_cart_with_negative_quantity(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "quantity": -5,  # Invalid negative quantity
    }
    with pytest.raises(ValueError):
        await add_to_cart.handle(args, context)


async def test_add_to_cart_with_non_integer_quantity(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "quantity": 2.5,  # Invalid non-integer quantity
    }
    with pytest.raises(ValueError):
        await add_to_cart.handle(args, context)


async def test_add_to_cart_with_string_quantity(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "quantity": "two",  # Invalid string quantity
    }
    with pytest.raises(ValueError):
        await add_to_cart.handle(args, context)


async def test_add_to_cart_with_missing_product_id(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        # Missing product_id
        "variant_id": "var_1",
        "quantity": 2,
    }
    with pytest.raises(ValueError):
        await add_to_cart.handle(args, context)


async def test_add_to_cart_with_missing_variant_id(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        # Missing variant_id
        "quantity": 2,
    }
    with pytest.raises(ValueError):
        await add_to_cart.handle(args, context)


async def test_add_to_cart_with_empty_args(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {}  # Empty arguments
    with pytest.raises(ValueError):
        await add_to_cart.handle(args, context)


async def test_add_to_cart_with_none_args(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = None  # None arguments
    with pytest.raises(ValueError):
        await add_to_cart.handle(args, context)


# test tool should have correct metadata
async def test_add_to_cart_tool_spec_metadata():
    spec = add_to_cart.ADD_TO_CART

    assert spec.name == "add_to_cart"
    assert spec.handler is add_to_cart.handle
    assert spec.is_write is True
    assert "product_id" in spec.input_schema["properties"]
    assert "variant_id" in spec.input_schema["properties"]
    assert "quantity" in spec.input_schema["properties"]


# test handle forwards access token and request id to client
async def test_add_to_cart_handle_forwards_access_token_and_request_id(
    fake_cart_client,
):
    await add_to_cart.handle(
        {
            "product_id": "prod_1",
            "variant_id": "var_1",
            "quantity": 2,
        },
        ToolContext(request_id="req_123", access_token="token_123"),
    )

    assert fake_cart_client.calls == [("token_123", "prod_1", "var_1", 2, "req_123")]
