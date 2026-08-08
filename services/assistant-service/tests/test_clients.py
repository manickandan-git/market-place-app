import httpx

from app.clients import InventoryClient, ProductClient
from app.config import Settings
from app.exceptions import ServiceError


def _settings() -> Settings:
    return Settings(
        product_service_url="http://fake-product-service",
        inventory_service_url="http://fake-inventory-service",
    )


# ---------------------------------------------------------------------------
# ProductClient.search_products
# ---------------------------------------------------------------------------


async def test_search_products_sends_query_and_category_and_returns_items():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200, json={"items": [{"id": "1", "name": "Shoes"}], "pagination": {}}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    product_client = ProductClient(_settings(), client=client)

    result = await product_client.search_products("shoes", "cat-1", "req-123")

    assert result == [{"id": "1", "name": "Shoes"}]
    assert captured[0].url.params["q"] == "shoes"
    assert captured[0].url.params["category_id"] == "cat-1"
    assert captured[0].url.params["page_size"] == "10"
    assert captured[0].headers.get("x-request-id") == "req-123"
    await client.aclose()


async def test_search_products_omits_optional_params_when_not_given():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"items": [], "pagination": {}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    product_client = ProductClient(_settings(), client=client)

    await product_client.search_products(None, None, None)

    assert "q" not in captured[0].url.params
    assert "category_id" not in captured[0].url.params
    assert "x-request-id" not in captured[0].headers
    await client.aclose()


async def test_search_products_raises_service_error_on_upstream_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    product_client = ProductClient(_settings(), client=client)

    try:
        await product_client.search_products("shoes", None, None)
        raise AssertionError("expected ServiceError")
    except ServiceError as exc:
        assert exc.status_code == 502
        assert exc.code == "product_service_error"
    await client.aclose()


async def test_search_products_raises_service_error_on_network_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    product_client = ProductClient(_settings(), client=client)

    try:
        await product_client.search_products("shoes", None, None)
        raise AssertionError("expected ServiceError")
    except ServiceError as exc:
        assert exc.status_code == 503
        assert exc.code == "product_service_unavailable"
    await client.aclose()


# ---------------------------------------------------------------------------
# ProductClient.get_product_by_slug
# ---------------------------------------------------------------------------


async def test_get_product_by_slug_returns_product_on_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/products/by-slug/running-shoes"
        return httpx.Response(200, json={"id": "1", "slug": "running-shoes"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    product_client = ProductClient(_settings(), client=client)

    result = await product_client.get_product_by_slug("running-shoes", None)

    assert result == {"id": "1", "slug": "running-shoes"}
    await client.aclose()


async def test_get_product_by_slug_returns_none_on_404():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "product_not_found"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    product_client = ProductClient(_settings(), client=client)

    result = await product_client.get_product_by_slug("does-not-exist", None)

    assert result is None
    await client.aclose()


async def test_get_product_by_slug_raises_service_error_on_upstream_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    product_client = ProductClient(_settings(), client=client)

    try:
        await product_client.get_product_by_slug("running-shoes", None)
        raise AssertionError("expected ServiceError")
    except ServiceError as exc:
        assert exc.status_code == 502
        assert exc.code == "product_service_error"
    await client.aclose()


# ---------------------------------------------------------------------------
# ProductClient.list_categories
# ---------------------------------------------------------------------------


async def test_list_categories_returns_plain_list():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/categories"
        return httpx.Response(200, json=[{"id": "1", "name": "Footwear"}])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    product_client = ProductClient(_settings(), client=client)

    result = await product_client.list_categories(None)

    assert result == [{"id": "1", "name": "Footwear"}]
    await client.aclose()


async def test_list_categories_raises_service_error_on_upstream_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    product_client = ProductClient(_settings(), client=client)

    try:
        await product_client.list_categories(None)
        raise AssertionError("expected ServiceError")
    except ServiceError as exc:
        assert exc.status_code == 502
        assert exc.code == "product_service_error"
    await client.aclose()


# ---------------------------------------------------------------------------
# InventoryClient.get_availability
# ---------------------------------------------------------------------------


async def test_get_availability_returns_upstream_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/availability/SKU-1"
        return httpx.Response(
            200, json={"sku": "SKU-1", "available_quantity": 5, "is_available": True}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    inventory_client = InventoryClient(_settings(), client=client)

    result = await inventory_client.get_availability("SKU-1", None)

    assert result == {"sku": "SKU-1", "available_quantity": 5, "is_available": True}
    await client.aclose()


async def test_get_availability_raises_service_error_on_upstream_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    inventory_client = InventoryClient(_settings(), client=client)

    try:
        await inventory_client.get_availability("SKU-1", None)
        raise AssertionError("expected ServiceError")
    except ServiceError as exc:
        assert exc.status_code == 502
        assert exc.code == "inventory_service_error"
    await client.aclose()


async def test_get_availability_raises_service_error_on_network_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://fake-service")
    inventory_client = InventoryClient(_settings(), client=client)

    try:
        await inventory_client.get_availability("SKU-1", None)
        raise AssertionError("expected ServiceError")
    except ServiceError as exc:
        assert exc.status_code == 503
        assert exc.code == "inventory_service_unavailable"
    await client.aclose()
