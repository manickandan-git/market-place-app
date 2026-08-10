from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str ="Marketplace Assistant Service"
    environment: str="development"
    app_version: str="1.0.0"
    debug: bool = False
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://marketplace:marketplace@localhost:5442/assistant_service"
    jwt_jwks_url: str="http://localhost:8001/.well-known/jwks.json"
    jwt_issuer: str="http://localhost:8001"
    jwt_audience: str="marketplace-api"
    jwt_algorithms: list[str]=["RS256"]
    jwks_cache_seconds: int=300
    product_service_url: str="http://localhost:8004"
    inventory_service_url: str="http://localhost:8005"
    order_service_url: str="http://localhost:8007"
    cart_service_url: str="http://localhost:8006"
    downstream_timeout_seconds: float = 5.0
    cors_origins: list[str]=["http://localhost:3000"]
    sql_echo: bool = False
    embedding_model_name: str = "all-MiniLM-L6-v2"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    chat_rate_limit_requests: int = 20
    chat_rate_limit_window_seconds: int = 60
    chat_request_timeout_seconds: float = 45.0

@lru_cache
def get_settings() -> Settings:
    return Settings()

    