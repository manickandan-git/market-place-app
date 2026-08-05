from fastapi.testclient import TestClient

from app.main import app


def test_health_ok():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"


def test_unknown_path_404s():
    with TestClient(app) as client:
        response = client.get("/api/v1/does-not-exist")
        assert response.status_code == 404


def test_internal_path_404s():
    with TestClient(app) as client:
        response = client.post("/api/v1/internal/carts/expire")
        assert response.status_code == 404


def test_service_token_path_404s():
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/service-token")
        assert response.status_code == 404
