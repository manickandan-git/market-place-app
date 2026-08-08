import pytest
from pydantic import ValidationError

from app.tools import get_product
from app.tools.types import ToolContext

_UNSET = object()


class FakeProductClient:
    def __init__(self, response=_UNSET):
        self.calls: list[tuple] = []
        self._response = {} if response is _UNSET else response

    async def get_product_by_slug(self, slug, request_id):
        self.calls.append((slug, request_id))
        return self._response


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeProductClient({"id": "1", "name": "Shoes"})
    monkeypatch.setattr(get_product, "_client", fake)
    return fake


@pytest.mark.usefixtures("fake_client")
async def test_handle_returns_item_from_client():
    result = await get_product.handle(
        {"slug": "shoes"}, ToolContext(request_id="req-1")
    )

    assert result == {"product": {"id": "1", "name": "Shoes"}}


async def test_handle_forwards_args_and_request_id_to_client(fake_client):
    await get_product.handle(
        {"slug": "shoes"}, ToolContext(request_id="req-1")
    )

    assert fake_client.calls == [("shoes", "req-1")]


@pytest.mark.usefixtures("fake_client")
async def test_handle_raises_validation_error_when_slug_missing():
    with pytest.raises(ValidationError):
        await get_product.handle({}, ToolContext(request_id=None))


async def test_handle_returns_none_product_when_not_found(monkeypatch):
    fake = FakeProductClient(response=None)
    monkeypatch.setattr(get_product, "_client", fake)

    result = await get_product.handle(
        {"slug": "does-not-exist"}, ToolContext(request_id=None)
    )

    assert result == {"product": None}


def test_get_product_tool_spec_metadata():
    spec = get_product.GET_PRODUCT

    assert spec.name == "get_product"
    assert spec.handler is get_product.handle
    assert spec.input_schema["type"] == "object"
    assert "slug" in spec.input_schema["properties"]


def test_get_product_to_anthropic_tool_shape():
    tool = get_product.GET_PRODUCT.to_anthropic_tool()

    assert set(tool.keys()) == {"name", "description", "input_schema"}
    assert tool["name"] == "get_product"
