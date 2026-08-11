"""
Tests for the remove_from_cart tool.
"""

import pytest

from app.tools import remove_from_cart
from app.tools.types import ToolContext


class FakeCartClient:
    def __init__(self, response=None):
        self.calls: list[tuple] = []
        self._response = response or {}

    async def remove_item(self, access_token, product_id, variant_id, request_id):
        self.calls.append((access_token, product_id, variant_id, request_id))
        return self._response


@pytest.fixture
def fake_cart_client(monkeypatch):
    client = FakeCartClient()
    monkeypatch.setattr(remove_from_cart, "_client", client)
    return client


@pytest.mark.usefixtures("fake_cart_client")
async def test_remove_from_cart(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
    }
    result = await remove_from_cart.handle(args, context)
    assert result["authenticated"] is True
    assert result["removed"] is True
    assert result["cart"] == fake_cart_client._response
    assert fake_cart_client.calls == [("fake_token", "prod_1", "var_1", "req_123")]


async def test_remove_from_cart_requires_authentication(fake_cart_client):
    context = ToolContext(access_token=None, request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
    }
    result = await remove_from_cart.handle(args, context)
    assert result["authenticated"] is False
    assert "message" in result
    assert fake_cart_client.calls == []


async def test_remove_from_cart_allows_empty_product_id(fake_cart_client):
    # RemoveFromCartArgs.product_id is a plain `str` with no min_length,
    # same as AddToCartArgs — an empty string is valid input, not a
    # validation error. Documents the actual (permissive) behavior rather
    # than asserting a constraint that doesn't exist.
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "",
        "variant_id": "var_1",
    }
    result = await remove_from_cart.handle(args, context)
    assert result["authenticated"] is True


async def test_remove_from_cart_invalid_args_missing_variant(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        # Missing variant_id
    }
    with pytest.raises(ValueError):
        await remove_from_cart.handle(args, context)


async def test_remove_from_cart_invalid_args_missing_product(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        # Missing product_id
        "variant_id": "var_1",
    }
    with pytest.raises(ValueError):
        await remove_from_cart.handle(args, context)


async def test_remove_from_cart_allows_empty_variant_id(fake_cart_client):
    # Same reasoning as test_remove_from_cart_allows_empty_product_id.
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "",
    }
    result = await remove_from_cart.handle(args, context)
    assert result["authenticated"] is True


async def test_remove_from_cart_item_not_found(fake_cart_client):
    # CartClient.remove_item returns None when no cart line matches
    # product_id/variant_id — handle() turns that into a soft "not found"
    # result with no "cart" key at all, not a None cart.
    fake_cart_client._response = None
    result = await remove_from_cart.handle(
        {"product_id": "p1", "variant_id": "v1"},
        ToolContext(access_token="t", request_id="r"),
    )
    assert result == {
        "authenticated": True,
        "removed": False,
        "message": "That item isn't in your cart.",
    }


async def test_remove_from_cart_success_with_empty_cart_response(fake_cart_client):
    # {} is not None, so this is a *success* case (an edge case in the
    # fake, not a realistic CartClient response) — not "item not found".
    fake_cart_client._response = {}
    result = await remove_from_cart.handle(
        {"product_id": "p1", "variant_id": "v1"},
        ToolContext(access_token="t", request_id="r"),
    )
    assert result == {
        "authenticated": True,
        "removed": True,
        "cart": {},
    }


async def test_remove_from_cart_with_extra_unexpected_args(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        "variant_id": "var_1",
        "extra_arg1": "value1",
        "extra_arg2": "value2",
    }
    result = await remove_from_cart.handle(args, context)
    assert result["authenticated"] is True
    assert result["removed"] is True
    assert result["cart"] == fake_cart_client._response


async def test_remove_from_cart_with_none_args(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = None  # None arguments
    with pytest.raises(ValueError):
        await remove_from_cart.handle(args, context)


async def test_remove_from_cart_with_empty_args(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {}  # Empty arguments
    with pytest.raises(ValueError):
        await remove_from_cart.handle(args, context)


async def test_remove_from_cart_with_missing_product_id(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        # Missing product_id
        "variant_id": "var_1",
    }
    with pytest.raises(ValueError):
        await remove_from_cart.handle(args, context)


async def test_remove_from_cart_with_missing_variant_id(fake_cart_client):
    context = ToolContext(access_token="fake_token", request_id="req_123")
    args = {
        "product_id": "prod_1",
        # Missing variant_id
    }
    with pytest.raises(ValueError):
        await remove_from_cart.handle(args, context)


async def test_remove_from_cart_spec_metadata():
    spec = remove_from_cart.REMOVE_FROM_CART
    assert spec.name == "remove_from_cart"
    assert "Remove an item from the shopping cart" in spec.description
    assert spec.is_write is True
    assert "product_id" in spec.input_schema["properties"]
    assert "variant_id" in spec.input_schema["properties"]


async def test_remove_from_cart_handle_forwards_access_token_and_request_id(
    fake_cart_client,
):
    await remove_from_cart.handle(
        {"product_id": "prod_1", "variant_id": "var_1"},
        ToolContext(request_id="req_123", access_token="token_123"),
    )

    assert fake_cart_client.calls == [("token_123", "prod_1", "var_1", "req_123")]
