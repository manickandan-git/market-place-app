import httpx
from starlette.requests import Request

from app.config import Settings
from app.exceptions import ServiceError
from app.services.proxy_service import ProxyService


async def _empty_receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_request(method: str = "GET", path: str = "/api/v1/products") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "state": {"request_id": "test-request-id"},
    }
    return Request(scope, receive=_empty_receive)


async def test_successful_calls_return_upstream_response_and_stay_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        circuit_breaker_failure_threshold=1, circuit_breaker_cooldown_seconds=30
    )
    service = ProxyService(client, settings)

    for _ in range(5):
        response = await service.forward(
            _make_request(), "http://fake-product-service", "product_service_url"
        )
        assert response.status_code == 200

    await client.aclose()


async def test_circuit_opens_after_threshold_and_fails_fast_without_network():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("boom", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        circuit_breaker_failure_threshold=2, circuit_breaker_cooldown_seconds=30
    )
    service = ProxyService(client, settings)

    for _ in range(2):
        try:
            await service.forward(
                _make_request(), "http://fake-product-service", "product_service_url"
            )
            raise AssertionError("expected ServiceError")
        except ServiceError as exc:
            assert exc.status_code == 502

    assert call_count == 2

    # Circuit is now open: the third call must fail fast with 503 and never
    # touch the transport at all.
    try:
        await service.forward(
            _make_request(), "http://fake-product-service", "product_service_url"
        )
        raise AssertionError("expected ServiceError")
    except ServiceError as exc:
        assert exc.status_code == 503
        assert exc.code == "circuit_open"
    assert call_count == 2

    await client.aclose()


async def test_circuit_breakers_are_independent_per_upstream():
    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(failing_handler))
    settings = Settings(
        circuit_breaker_failure_threshold=1, circuit_breaker_cooldown_seconds=30
    )
    service = ProxyService(client, settings)

    try:
        await service.forward(
            _make_request(), "http://fake-product-service", "product_service_url"
        )
    except ServiceError:
        pass

    # product_service_url's circuit is open, but a different service key
    # must still attempt the network call normally.
    try:
        await service.forward(
            _make_request(), "http://fake-inventory-service", "inventory_service_url"
        )
        raise AssertionError("expected ServiceError")
    except ServiceError as exc:
        assert exc.status_code == 502  # reached the transport, got ConnectError

    await client.aclose()
