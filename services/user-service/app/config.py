from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="USER_SERVICE_",
        extra="ignore",
    )

    service_name: str = "marketplace-user-service"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    docs_enabled: bool = True
    database_url: str = Field(
        default="postgresql+asyncpg://marketplace:marketplace@localhost:5435/user_service"
    )
    # Aliased to the bare JWT_* names (no USER_SERVICE_ prefix) so they match
    # the convention every other service uses for these three settings.
    identity_issuer: str = Field(
        default="http://localhost:8001", validation_alias="JWT_ISSUER"
    )
    identity_audience: str = Field(
        default="marketplace-api", validation_alias="JWT_AUDIENCE"
    )
    identity_jwks_url: str = Field(
        default="http://localhost:8001/.well-known/jwks.json",
        validation_alias="JWT_JWKS_URL",
    )
    jwt_algorithms: list[str] = ["RS256"]
    database_echo: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    idempotency_ttl_hours: int = 24
    version: str = "1.0.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
