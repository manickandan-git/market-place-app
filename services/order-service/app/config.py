from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Marketplace Order Service"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+asyncpg://orders:orders@localhost:5436/order_service"
    )
    jwt_jwks_url: str = "http://localhost:8000/.well-known/jwks.json"
    jwt_issuer: str = "http://localhost:8000"
    jwt_audience: str = "marketplace-api"
    jwt_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    jwks_cache_seconds: int = Field(default=300, ge=30, le=3600)
    auth_service_url: str = "http://localhost:8001"
    cart_service_url: str = "http://localhost:8006"
    product_service_url: str = "http://localhost:8004"
    inventory_service_url: str = "http://localhost:8005"
    notification_service_url: str = "http://localhost:8003"
    notification_internal_api_key: str = "change-me"
    # Client credentials this service uses to authenticate itself to
    # auth-service's POST /api/v1/auth/service-token, to obtain a token
    # carrying inventory:checkout + inventory:commit + cart:checkout.
    # inventory:checkout is needed to create a checkout reservation in the
    # first place — Inventory's create-batch-reservation endpoint only
    # accepts that scope (or admin), not a forwarded buyer JWT. inventory:commit
    # is needed for payment_authorized/payment_failed: those are called by
    # Payment Service's own orders:payment-scoped token, which must not be
    # forwarded straight through to Inventory's commit/release endpoints
    # (Inventory doesn't grant that scope any authority there — only the
    # reservation's own buyer, an admin/seller, or inventory:commit can).
    # cart:checkout is needed to call Cart's internal checked-out callback
    # after placing an order — see AuthClient/CartClient.mark_checked_out.
    order_service_client_id: str = "order-service"
    order_service_client_secret: str = "change-this-in-production-order-service-secret"
    downstream_timeout_seconds: float = Field(default=8.0, gt=0, le=30)
    reservation_minutes: int = Field(default=15, ge=5, le=60)
    order_number_prefix: str = "ORD"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    sql_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
