"""
test use case of get my orders tool
"""

import pytest

from app.tools import get_my_orders
from app.tools.types import ToolContext


class FakeOrderClient:
    def __init__(self, response=None):
        self.calls: list[tuple] = []
        self._response = response or {}

    async def get_my_orders(self, access_token, request_id):
        self.calls.append((access_token, request_id))
        return self._response


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeOrderClient(
        {
            "items": [
                {
                    "id": "order1",
                    "grand_total": 100,
                    "billing_address": {"street": "should be trimmed"},
                },
                {
                    "id": "order2",
                    "grand_total": 200,
                    "billing_address": {"street": "should be trimmed"},
                },
            ],
            "total_items": 2,
        }
    )
    monkeypatch.setattr(get_my_orders, "_client", fake)
    return fake


@pytest.mark.usefixtures("fake_client")
async def test_handle_returns_orders_when_authenticated():
    result = await get_my_orders.handle(
        {},
        ToolContext(request_id="req-1", access_token="token-1"),
    )

    # billing_address is dropped by summarize_order (see _order_utils.py) -
    # only fields the assistant actually needs survive the trim.
    assert result == {
        "authenticated": True,
        "orders": [
            {"id": "order1", "grand_total": 100},
            {"id": "order2", "grand_total": 200},
        ],
        "total": 2,
    }


async def test_handle_returns_authenticated_false_when_no_access_token():
    result = await get_my_orders.handle(
        {},
        ToolContext(request_id="req-1", access_token=None),
    )

    assert result == {
        "authenticated": False,
        "message": "You need to sign in to view your orders.",
    }


@pytest.mark.usefixtures("fake_client")
async def test_handle_ignores_unexpected_args():
    result = await get_my_orders.handle(
        {"unexpected_arg": "value"},
        ToolContext(request_id="req-1", access_token="token-1"),
    )

    assert result["authenticated"] is True


async def test_get_my_orders_tool_spec_metadata():
    spec = get_my_orders.GET_MY_ORDERS

    assert spec.name == "get_my_orders"
    assert spec.handler is get_my_orders.handle
    assert spec.input_schema["type"] == "object"


def test_get_my_orders_to_anthropic_tool_shape():
    tool = get_my_orders.GET_MY_ORDERS.to_anthropic_tool()

    assert set(tool.keys()) == {"name", "description", "input_schema"}
    assert tool["name"] == "get_my_orders"


async def test_handle_forwards_access_token_and_request_id_to_client(fake_client):
    await get_my_orders.handle(
        {},
        ToolContext(request_id="req-1", access_token="token-1"),
    )

    assert fake_client.calls == [("token-1", "req-1")]
