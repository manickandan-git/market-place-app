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

    app_name: str = "Marketplace API Gateway"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    downstream_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    # Centralized, edge-level check only: signature/exp/iss/aud via JWKS,
    # run once before proxying when a request carries a bearer token. Not a
    # replacement for each downstream service's own JWT verification +
    # role/scope/ownership authorization, which still runs unchanged on
    # every request that reaches it — see app/services/token_verifier.py.
    # Must match auth-service's own JWT_ISSUER/JWT_AUDIENCE byte-for-byte,
    # same convention as every other verifying service in this codebase.
    jwt_jwks_url: str = "http://localhost:8001/.well-known/jwks.json"
    jwt_issuer: str = "http://localhost:8001"
    jwt_audience: str = "marketplace-api"
    jwt_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    jwks_cache_seconds: int = Field(default=300, ge=30, le=3600)

    circuit_breaker_failure_threshold: int = Field(default=5, ge=1, le=50)
    circuit_breaker_cooldown_seconds: float = Field(default=30.0, gt=0, le=600)

    # Deliberately no notification_service_url: notification-service has no
    # end-user-facing routes (every route requires X-Internal-API-Key) and
    # is never registered in the routing table — see docs/route-allowlist.md.
    auth_service_url: str = "http://localhost:8001"
    user_service_url: str = "http://localhost:8003"
    product_service_url: str = "http://localhost:8004"
    inventory_service_url: str = "http://localhost:8005"
    cart_service_url: str = "http://localhost:8006"
    order_service_url: str = "http://localhost:8007"
    payment_service_url: str = "http://localhost:8008"
    shipping_service_url: str = "http://localhost:8009"
    assistant_service_url: str = "http://localhost:8012"


@lru_cache
def get_settings() -> Settings:
    return Settings()
