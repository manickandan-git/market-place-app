from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_private_endpoint_requires_token() -> None:
    with TestClient(create_app(Settings(docs_enabled=False))) as client:
        response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_correlation_id_is_returned() -> None:
    with TestClient(create_app(Settings(docs_enabled=False))) as client:
        response = client.get(
            "/api/v1/health/live", headers={"X-Correlation-ID": "test-correlation"}
        )
    assert response.headers["X-Correlation-ID"] == "test-correlation"
