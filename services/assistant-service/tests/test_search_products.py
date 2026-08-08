import pytest

from app.tools import search_products
from app.tools.types import ToolContext


class FakeProductClient:
    def __init__(self, response: list[dict] | None = None):
        self.calls: list[tuple] = []
        self._response = response if response is not None else []

    async def search_products(self, query, category_id, request_id):
        self.calls.append((query, category_id, request_id))
        return self._response


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeProductClient([{"id": "1", "name": "Shoes"}])
    monkeypatch.setattr(search_products, "_client", fake)
    return fake


@pytest.mark.usefixtures("fake_client")
async def test_handle_returns_items_from_client():
    result = await search_products.handle(
        {"query": "shoes", "category_id": "cat-1"}, ToolContext(request_id="req-1")
    )

    assert result == {"items": [{"id": "1", "name": "Shoes"}]}


async def test_handle_forwards_args_and_request_id_to_client(fake_client):
    await search_products.handle(
        {"query": "shoes", "category_id": "cat-1"}, ToolContext(request_id="req-1")
    )

    assert fake_client.calls == [("shoes", "cat-1", "req-1")]


async def test_handle_defaults_missing_args_to_none(fake_client):
    await search_products.handle({}, ToolContext(request_id=None))

    assert fake_client.calls == [(None, None, None)]


def test_search_products_tool_spec_metadata():
    spec = search_products.SEARCH_PRODUCTS

    assert spec.name == "search_products"
    assert spec.handler is search_products.handle
    assert spec.input_schema["type"] == "object"
    assert "query" in spec.input_schema["properties"]
    assert "category_id" in spec.input_schema["properties"]


def test_search_products_to_anthropic_tool_shape():
    tool = search_products.SEARCH_PRODUCTS.to_anthropic_tool()

    assert set(tool.keys()) == {"name", "description", "input_schema"}
    assert tool["name"] == "search_products"
