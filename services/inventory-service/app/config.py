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

    app_name: str = "Marketplace Inventory Service"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+asyncpg://marketplace:marketplace@localhost:5437/"
        "inventory_service"
    )
    jwt_jwks_url: str = "http://localhost:8001/.well-known/jwks.json"
    jwt_issuer: str = "http://localhost:8001"
    jwt_audience: str = "marketplace-api"
    jwt_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    jwks_cache_seconds: int = Field(default=300, ge=30, le=3600)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    default_reservation_minutes: int = Field(default=15, ge=1, le=60)
    max_reservation_minutes: int = Field(default=60, ge=1, le=1440)
    low_stock_default_threshold: int = Field(default=5, ge=0, le=1_000_000)
    sql_echo: bool = False
    auth_service_url: str = "http://localhost:8001"
    downstream_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    inventory_expire_client_id: str = "inventory-expire-scheduler"
    inventory_expire_client_secret: str = "inventory-expire-scheduler-secret-12345"
    celery_broker_url: str = "redis://localhost:6379/0"
    expire_sweeper_interval_seconds: int = Field(default=60, ge=10, le=3600)
    inventory_service_url: str = "http://localhost:8005"


@lru_cache
def get_settings() -> Settings:
    return Settings()
