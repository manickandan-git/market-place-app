from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.integration",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    auth_service_url: str = "http://localhost:8001"
    user_service_url: str = "http://localhost:8002"
    product_service_url: str = "http://localhost:8003"
    inventory_service_url: str = "http://localhost:8004"
    notification_service_url: str = "http://localhost:8005"

    auth_health_path: str = "/health"
    auth_jwks_path: str = "/.well-known/jwks.json"
    user_health_path: str = "/health/live"
    product_health_path: str = "/health"
    inventory_health_path: str = "/health"
    notification_health_path: str = "/health"

    jwt_issuer: str = "http://localhost:8001"
    jwt_audience: str = "marketplace-api"
    jwt_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])

    buyer_access_token: str | None = None
    seller_a_access_token: str | None = None
    seller_b_access_token: str | None = None
    admin_access_token: str | None = None
    inventory_sync_access_token: str | None = None

    auth_login_path: str = "/api/v1/auth/login"
    auth_login_email_field: str = "email"
    auth_login_password_field: str = "password"
    auth_login_token_field: str = "access_token"
    buyer_email: str | None = None
    buyer_password: str | None = None
    seller_a_email: str | None = None
    seller_a_password: str | None = None
    seller_b_email: str | None = None
    seller_b_password: str | None = None
    admin_email: str | None = None
    admin_password: str | None = None

    internal_api_key: str | None = None
    notification_test_endpoint: str | None = None
    notification_api_key_header: str = "X-Internal-API-Key"

    http_timeout_seconds: float = 20
    startup_timeout_seconds: float = 90
    verify_tls: bool = True

    def url(self, base: str, path: str) -> str:
        return f"{base.rstrip('/')}/{path.lstrip('/')}"


@lru_cache
def get_settings() -> Settings:
    return Settings()

