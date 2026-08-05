from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Marketplace Shipping Service"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+asyncpg://shipping:shipping@localhost:5441/shipping_service"
    )
    jwt_jwks_url: str = "http://localhost:8001/.well-known/jwks.json"
    jwt_issuer: str = "http://localhost:8001"
    jwt_audience: str = "marketplace-api"
    jwt_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    jwks_cache_seconds: int = Field(default=300, ge=30, le=3600)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    auth_service_url: str = "http://localhost:8001"
    order_service_url: str = "http://localhost:8007"
    downstream_timeout_seconds: float = Field(default=8.0, gt=0, le=30)

    # Client credentials this service uses to authenticate itself to
    # auth-service's POST /api/v1/auth/service-token, to obtain a token
    # carrying the orders:fulfillment scope for calling Order's internal
    # fulfillment callback. Must match the
    # SHIPPING_SERVICE_CLIENT_ID/SECRET registered in auth-service.
    shipping_service_client_id: str = "shipping-service"
    shipping_service_client_secret: str = (
        "change-this-in-production-shipping-service-secret"
    )

    sql_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
