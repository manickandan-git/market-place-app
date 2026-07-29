from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness() -> None:
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    assert response.json()["service"] == "Marketplace Inventory Service"


def test_request_id_is_returned() -> None:
    response = TestClient(app).get(
        "/health",
        headers={"X-Request-ID": "inventory-test-request"},
    )
    assert response.headers["X-Request-ID"] == "inventory-test-request"


def test_openapi_contains_core_routes() -> None:
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    assert "/api/v1/availability/{sku}" in paths
    assert "/api/v1/seller/inventory/{item_id}/adjustments" in paths
    assert "/api/v1/reservations/{reservation_id}/commit" in paths
