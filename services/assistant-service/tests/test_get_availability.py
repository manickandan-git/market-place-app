# Test Get Availability tool

import pytest

from app.tools import get_availability
from app.tools.types import ToolContext

_UNSET = object()


class FakeInventoryClient:
    def __init__(self, response=_UNSET):
        self.calls: list[tuple] = []
        self._response = {} if response is _UNSET else response

    async def get_availability(self, sku, request_id):
        self.calls.append((sku, request_id))
        return self._response


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeInventoryClient({"sku": "123", "available": True})
    monkeypatch.setattr(get_availability, "_client", fake)
    return fake

@pytest.mark.usefixtures("fake_client")
async def test_handle_returns_availability_from_client():
    result = await get_availability.handle(
        {"sku": "123"}, ToolContext(request_id="req-1")
    )

    assert result == {"availability": {"sku": "123", "available": True}}

async def test_handle_forwards_args_and_request_id_to_client(fake_client):
    await get_availability.handle(
        {"sku": "123"}, ToolContext(request_id="req-1")
    )

    assert fake_client.calls == [("123", "req-1")]

async def test_handle_raises_validation_error_when_sku_missing():
    with pytest.raises(ValueError):
        await get_availability.handle({}, ToolContext(request_id=None))

async def test_handle_returns_none_availability_when_not_found(monkeypatch):
    fake = FakeInventoryClient(response=None)
    monkeypatch.setattr(get_availability, "_client", fake)

    result = await get_availability.handle(
        {"sku": "does-not-exist"}, ToolContext(request_id=None)
    )

    assert result == {"availability": None}

async def test_handle_raises_validation_error_when_sku_is_not_string():
    with pytest.raises(ValueError):
        await get_availability.handle({"sku": 123}, ToolContext(request_id=None))

async def test_get_availability_tool_spec_metadata():
    spec = get_availability.GET_AVAILABILITY

    assert spec.name == "get_availability"
    assert spec.handler is get_availability.handle
    assert spec.input_schema["type"] == "object"
    assert "sku" in spec.input_schema["properties"]


