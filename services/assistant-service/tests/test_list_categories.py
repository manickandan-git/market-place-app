# test list categories tool
import pytest

from app.tools import list_categories
from app.tools.types import ToolContext


class FakeProductClient:
    def __init__(self, response: list[dict] | None = None):
        self.calls: list[tuple] = []
        self._response = response if response is not None else []

    async def list_categories(self, request_id):
        self.calls.append((request_id,))
        return self._response

@pytest.fixture 
def fake_client(monkeypatch):
    fake = FakeProductClient([{"id": "1", "name": "Electronics"}])
    monkeypatch.setattr(list_categories, "_client", fake)
    return fake

@pytest.mark.usefixtures("fake_client")
async def test_handle_returns_categories_from_client():
    result = await list_categories.handle({}, ToolContext(request_id="req-1"))

    assert result == {"categories": [{"id": "1", "name": "Electronics"}]}

async def test_handle_forwards_request_id_to_client(fake_client):
    await list_categories.handle({}, ToolContext(request_id="req-1"))

    assert fake_client.calls == [("req-1",)]

async def test_handle_returns_empty_list_when_no_categories(fake_client):
    fake_client._response = []

    result = await list_categories.handle({}, ToolContext(request_id=None))

    assert result == {"categories": []}

async def test_handle_returns_none_when_client_returns_none(fake_client):
    fake_client._response = None

    result = await list_categories.handle({}, ToolContext(request_id=None))

    assert result == {"categories": None}

@pytest.mark.usefixtures("fake_client")
async def test_handle_ignores_unexpected_args():
    result = await list_categories.handle(
        {"unexpected_arg": "value"}, ToolContext(request_id=None)
    )

    assert result == {"categories": [{"id": "1", "name": "Electronics"}]}

async def test_list_categories_tool_spec_metadata():
    spec = list_categories.LIST_CATEGORIES

    assert spec.name == "list_categories"
    assert spec.handler is list_categories.handle
    assert spec.input_schema["type"] == "object"
    assert spec.input_schema["properties"] == {}

def test_list_categories_to_anthropic_tool_shape():
    tool = list_categories.LIST_CATEGORIES.to_anthropic_tool()

    assert set(tool.keys()) == {"name", "description", "input_schema"}
    assert tool["name"] == "list_categories"
    


