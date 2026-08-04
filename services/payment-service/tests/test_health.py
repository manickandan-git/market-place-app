from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness() -> None:
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    assert response.json()["service"] == "Marketplace Payment Service"


def test_openapi_contains_core_routes() -> None:
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    assert "/api/v1/payments" in paths
    assert "/api/v1/payments/{payment_id}" in paths
    assert "/api/v1/payments/{payment_id}/refund" in paths
    assert "/api/v1/webhooks/stripe" in paths
