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
    identity_issuer: str = "http://localhost:8001"
    identity_audience: str = "marketplace-api"
    identity_jwks_url: str = "http://localhost:8001/.well-known/jwks.json"
    jwt_algorithms: list[str] = ["RS256"]
    database_echo: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    idempotency_ttl_hours: int = 24
    version: str = "1.0.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
