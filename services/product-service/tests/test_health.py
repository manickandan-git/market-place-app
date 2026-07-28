from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "product-service"
    assert response.headers["X-Request-ID"]


def test_correlation_id_is_preserved() -> None:
    response = TestClient(app).get(
        "/health",
        headers={"X-Request-ID": "product-test-request"},
    )
    assert response.headers["X-Request-ID"] == "product-test-request"


def test_openapi_contains_catalog_routes() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/products" in paths
    assert "/api/v1/seller/products" in paths
    assert "/api/v1/admin/categories" in paths

