from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Notification Service configuration.

    Values are loaded from:

    1. Operating-system environment variables
    2. The local .env file
    3. Defaults declared in this class
    """

    # ========================================================
    # Application
    # ========================================================

    app_name: str = "Marketplace Notification Service"

    app_env: Literal[
        "development",
        "test",
        "staging",
        "production",
    ] = "development"

    app_version: str = "0.1.0"

    api_v1_prefix: str = "/api/v1"

    host: str = "0.0.0.0"

    port: int = 8002

    log_level: str = "INFO"

    # ========================================================
    # Database
    # ========================================================

    database_url: str = (
        "postgresql+asyncpg://marketplace:marketplace"
        "@localhost:5433/marketplace_notifications"
    )

    database_echo: bool = False

    # ========================================================
    # CORS
    # ========================================================

    cors_allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]    
    
    # ========================================================
    # Redis and Celery
    # ========================================================

    redis_url: str = "redis://localhost:6380/1"

    celery_broker_url: str = "redis://localhost:6380/1"

    celery_result_backend: str = "redis://localhost:6380/2"

    celery_task_always_eager: bool = False

    celery_task_eager_propagates: bool = True

    celery_task_max_retries: int = Field(
        default=5,
        ge=0,
        le=20,
    )

    celery_retry_delay_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
    )

    celery_task_time_limit_seconds: int = 120

    celery_task_soft_time_limit_seconds: int = 90

    celery_default_retry_delay_seconds: int = 30

    celery_email_rate_limit: str = "100/m"


    # ========================================================
    # Email provider
    # ========================================================

    email_provider: Literal[
        "console",
        "smtp",
    ] = "console"

    default_from_email: EmailStr = "your-gmail-address@gmail.com"

    default_from_name: str = "Marketplace"

    support_email: EmailStr = "your-gmail-address@gmail.com"

    notification_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
    )

    @property
    def notification_maximum_retry_count(self) -> int:
        return self.notification_max_retries

    
    # ========================================================
    # SMTP
    # ========================================================

    smtp_host: str = "smtp.gmail.com"

    smtp_port: int = Field(
        default=587,
        ge=1,
        le=65535,
    )

    smtp_username: str | None = None

    smtp_password: str | None = None

    smtp_use_tls: bool = True

    smtp_use_ssl: bool = False

    smtp_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
    )

    # ========================================================
    # Marketplace URLs
    # ========================================================

    marketplace_web_url: str = "http://localhost:3000"

    email_verification_path: str = "/verify-email"

    password_reset_path: str = "/reset-password"

    # ========================================================
    # Service-to-service security
    # ========================================================

    internal_api_key: str = Field(
        default="replace-this-development-api-key",
        min_length=16,
    )

    identity_service_url: str = "http://localhost:8001"

    # ========================================================
    # Notification rules
    # ========================================================

    maximum_recipient_count: int = Field(
        default=10,
        ge=1,
        le=100,
    )

    notification_retention_days: int = Field(
        default=90,
        ge=1,
        le=3650,
    )

    verification_email_subject: str = (
        "Verify your Marketplace account"
    )

    password_reset_email_subject: str = (
        "Reset your Marketplace password"
    )

    password_changed_email_subject: str = (
        "Your Marketplace password was changed"
    )

    # ========================================================
    # Pydantic settings
    # ========================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def verification_url_base(self) -> str:
        """
        Example result:

        http://localhost:3000/verify-email
        """

        return (
            f"{self.marketplace_web_url.rstrip('/')}"
            f"/{self.email_verification_path.lstrip('/')}"
        )

    @property
    def password_reset_url_base(self) -> str:
        """
        Example result:

        http://localhost:3000/reset-password
        """

        return (
            f"{self.marketplace_web_url.rstrip('/')}"
            f"/{self.password_reset_path.lstrip('/')}"
        )

    @model_validator(mode="after")
    def validate_smtp_settings(self) -> Settings:
        if self.smtp_use_tls and self.smtp_use_ssl:
            raise ValueError(
                "SMTP_USE_TLS and SMTP_USE_SSL cannot both be true."
            )

        if self.email_provider == "smtp":
            has_username = bool(
                self.smtp_username and self.smtp_username.strip()
            )
            has_password = bool(
                self.smtp_password and self.smtp_password.strip()
            )

            if has_username != has_password:
                raise ValueError(
                    "Set both SMTP_USERNAME and SMTP_PASSWORD, or leave both empty."
                )

            if self.smtp_host == "smtp.gmail.com":
                if not has_username or not has_password:
                    raise ValueError(
                        "Gmail SMTP requires SMTP_USERNAME and SMTP_PASSWORD. "
                        "Use a Gmail App Password."
                    )
                valid_gmail_ports = {465, 587}
                if self.smtp_port not in valid_gmail_ports:
                    raise ValueError(
                        "For Gmail SMTP, use port 587 (TLS) or 465 (SSL)."
                    )
                if self.smtp_port == 587 and not self.smtp_use_tls:
                    raise ValueError(
                        "For Gmail SMTP on port 587, set SMTP_USE_TLS=true."
                    )
                if self.smtp_port == 465 and not self.smtp_use_ssl:
                    raise ValueError(
                        "For Gmail SMTP on port 465, set SMTP_USE_SSL=true."
                    )

        return self


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Caching prevents reparsing the environment file for every request.
    """

    return Settings()