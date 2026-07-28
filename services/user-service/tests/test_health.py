from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_liveness_returns_service_identity() -> None:
    settings = Settings(
        service_name="test-user-service",
        environment="test",
        docs_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "test-user-service",
        "environment": "test",
    }


def test_readiness_is_available() -> None:
    with TestClient(create_app(Settings(docs_enabled=False))) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_docs_can_be_disabled() -> None:
    with TestClient(create_app(Settings(docs_enabled=False))) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 404
