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

    app_name: str = "Marketplace Cart Service"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://cart:cart@localhost:5435/cart_service"
    jwt_jwks_url: str = "http://localhost:8000/.well-known/jwks.json"
    jwt_issuer: str = "http://localhost:8000"
    jwt_audience: str = "marketplace-api"
    jwt_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    jwks_cache_seconds: int = Field(default=300, ge=30, le=3600)
    product_service_url: str = "http://localhost:8004"
    inventory_service_url: str = "http://localhost:8005"
    downstream_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    cart_ttl_days: int = Field(default=30, ge=1, le=365)
    guest_cart_ttl_days: int = Field(default=7, ge=1, le=30)
    max_distinct_items: int = Field(default=100, ge=1, le=500)
    max_item_quantity: int = Field(default=100, ge=1, le=1000)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    sql_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
