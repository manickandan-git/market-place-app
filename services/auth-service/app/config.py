from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.

    Environment variables override the default values defined here.
    During local development, values are normally loaded from the
    project's .env file.
    """

    # Application
    app_name: str = "Marketplace Auth Service"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = (
        "postgresql+asyncpg://marketplace:marketplace"
        "@localhost:5433/auth_service"
    )

    # Redis
    redis_url: str = "redis://localhost:6380/0"

    # JWT — refresh tokens only (auth-service is the sole consumer, so a
    # shared HMAC secret is fine here)
    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"

    # JWT — access tokens, verified by other services via JWKS
    jwt_access_algorithm: str = "RS256"
    jwt_private_key_path: str = "keys/jwt_private_key.pem"
    jwt_public_key_path: str = "keys/jwt_public_key.pem"
    jwt_kid: str = "auth-key-1"
    jwt_issuer: str = "http://localhost:8001"
    jwt_audience: str = "marketplace-api"

    # Token expiration
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Email verification
    email_verification_expire_minutes: int = 30

    # Password reset
    password_reset_expire_minutes: int = 30

    # Account protection
    max_failed_login_attempts: int = 5
    account_lock_minutes: int = 15

    # Notification Service integration
    notification_service_url: str = "http://localhost:8002"
    notification_service_api_key: str = "dev-only-internal-api-key-change-me"
    notification_service_timeout_seconds: float = 5.0

    # Service-to-service tokens (client credentials, no user session).
    # Currently a single registered client: Inventory Sync, which needs
    # the inventory:sync scope to call Inventory's internal catalog
    # projection endpoint.
    service_token_expire_minutes: int = 15
    inventory_sync_client_id: str = "inventory-sync-service"
    inventory_sync_client_secret: str = "change-this-in-production-inventory-sync-secret"
    inventory_sync_subject: str = "00000000-0000-0000-0000-000000000001"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached application settings instance.

    Caching prevents the .env file from being parsed repeatedly.
    """
    return Settings()