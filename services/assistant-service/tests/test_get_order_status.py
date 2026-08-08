import pytest
from pydantic import ValidationError

from app.exceptions import ServiceError
from app.tools import get_order_status
from app.tools.types import ToolContext

_UNSET = object()


class FakeOrderClient:
    def __init__(self, response=_UNSET, error: ServiceError | None = None):
        self.calls: list[tuple] = []
        self._response = None if response is _UNSET else response
        self._error = error

    async def get_order(self, order_id, access_token, request_id):
        self.calls.append((order_id, access_token, request_id))
        if self._error is not None:
            raise self._error
        return self._response


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeOrderClient({"id": "order-1", "status": "shipped"})
    monkeypatch.setattr(get_order_status, "_client", fake)
    return fake


@pytest.mark.usefixtures("fake_client")
async def test_handle_returns_order_when_authenticated():
    result = await get_order_status.handle(
        {"order_id": "order-1"},
        ToolContext(request_id="req-1", access_token="token-1"),
    )

    assert result == {
        "authenticated": True,
        "order": {"id": "order-1", "status": "shipped"},
    }


async def test_handle_forwards_order_id_access_token_and_request_id_to_client(
    fake_client,
):
    await get_order_status.handle(
        {"order_id": "order-1"},
        ToolContext(request_id="req-1", access_token="token-1"),
    )

    assert fake_client.calls == [("order-1", "token-1", "req-1")]


async def test_handle_returns_none_order_when_not_found(monkeypatch):
    fake = FakeOrderClient(response=None)
    monkeypatch.setattr(get_order_status, "_client", fake)

    result = await get_order_status.handle(
        {"order_id": "does-not-exist"},
        ToolContext(request_id="req-1", access_token="token-1"),
    )

    assert result == {"authenticated": True, "order": None}


async def test_handle_returns_authenticated_false_when_no_access_token():
    result = await get_order_status.handle(
        {"order_id": "order-1"},
        ToolContext(request_id="req-1", access_token=None),
    )

    assert result == {
        "authenticated": False,
        "message": "You need to sign in to check an order's status.",
    }


async def test_handle_does_not_call_client_when_no_access_token(monkeypatch):
    fake = FakeOrderClient()
    monkeypatch.setattr(get_order_status, "_client", fake)

    await get_order_status.handle(
        {"order_id": "order-1"}, ToolContext(request_id="req-1", access_token=None)
    )

    assert fake.calls == []


async def test_handle_raises_validation_error_when_order_id_missing():
    with pytest.raises(ValidationError):
        await get_order_status.handle(
            {}, ToolContext(request_id="req-1", access_token="token-1")
        )


async def test_handle_propagates_service_error_on_rejected_token(monkeypatch):
    fake = FakeOrderClient(
        error=ServiceError(
            401, "order_service_unauthorized", "Access token was rejected"
        )
    )
    monkeypatch.setattr(get_order_status, "_client", fake)

    with pytest.raises(ServiceError) as exc_info:
        await get_order_status.handle(
            {"order_id": "order-1"},
            ToolContext(request_id="req-1", access_token="bad-token"),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "order_service_unauthorized"


def test_get_order_status_tool_spec_metadata():
    spec = get_order_status.GET_ORDER_STATUS

    assert spec.name == "get_order_status"
    assert spec.handler is get_order_status.handle
    assert spec.input_schema["type"] == "object"
    assert "order_id" in spec.input_schema["properties"]
    assert spec.input_schema["required"] == ["order_id"]


def test_get_order_status_to_anthropic_tool_shape():
    tool = get_order_status.GET_ORDER_STATUS.to_anthropic_tool()

    assert set(tool.keys()) == {"name", "description", "input_schema"}
    assert tool["name"] == "get_order_status"
