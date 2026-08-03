from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "order-service"}
    assert response.headers["X-Request-ID"]


def test_openapi_contains_order_paths() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/orders" in paths
    assert "/api/v1/orders/{order_id}/cancel" in paths
    assert "/api/v1/internal/orders/{order_id}/payment-authorized" in paths
