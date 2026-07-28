
from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# Configure the test environment before importing application modules.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("EMAIL_PROVIDER", "console")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-api-key")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("CELERY_TASK_EAGER_PROPAGATES", "true")

from app.config import get_settings
from app.database import Base, get_db
from app.main import create_application
from app.models import (
    Notification,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
    ProviderType,
)
from app.providers.base import (
    EmailMessage,
    EmailProvider,
    PermanentProviderError,
    ProviderResult,
    RetryableProviderError,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class MockEmailProvider(EmailProvider):
    """
    In-memory email provider used by tests.

    The provider records every message that it receives and can be configured
    to return success, retryable failure, or permanent failure responses.
    """

    provider_type = ProviderType.CONSOLE

    def __init__(self) -> None:
        self.sent_messages: list[EmailMessage] = []
        self.is_healthy = True
        self.should_fail = False
        self.failure_retryable = False
        self.failure_message = "Mock provider delivery failure"
        self.response_code = "mock-error"

    def send(
        self,
        message: EmailMessage,
    ) -> ProviderResult:
        self.validate_message(message)
        self.sent_messages.append(message)

        if self.should_fail:
            if self.failure_retryable:
                raise RetryableProviderError(
                    self.failure_message,
                    response_code=self.response_code,
                )

            raise PermanentProviderError(
                self.failure_message,
                response_code=self.response_code,
            )

        return ProviderResult(
            success=True,
            provider=self.provider_type,
            provider_message_id=f"mock-{uuid4()}",
            response_code="250",
            response_message="Message accepted by mock provider",
            metadata={
                "mock": True,
            },
        )

    def health_check(self) -> bool:
        return self.is_healthy

    def reset(self) -> None:
        self.sent_messages.clear()
        self.is_healthy = True
        self.should_fail = False
        self.failure_retryable = False
        self.failure_message = "Mock provider delivery failure"
        self.response_code = "mock-error"


@pytest.fixture(scope="session", autouse=True)
def clear_settings_cache() -> Generator[None]:
    """
    Ensure each test session reads the test environment configuration.
    """

    get_settings.cache_clear()

    yield

    get_settings.cache_clear()


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine]:
    """
    Create a shared in-memory SQLite engine for integration tests.

    StaticPool keeps the same SQLite connection alive throughout the test
    session so the in-memory database remains available across fixtures.
    """

    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    test_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession]:
    """
    Provide an isolated asynchronous database session.

    All changes made during the test are rolled back when the fixture exits.
    """

    connection = await test_engine.connect()
    transaction = await connection.begin()

    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with session_factory() as session:
        yield session

        await session.rollback()

    if transaction.is_active:
        await transaction.rollback()

    await connection.close()


@pytest.fixture
def mock_email_provider() -> MockEmailProvider:
    """
    Return a fresh mock provider for each test.
    """

    return MockEmailProvider()


@pytest.fixture
def test_app(
    db_session: AsyncSession,
) -> FastAPI:
    """
    Create the FastAPI application with the test database dependency.
    """

    application = create_application()

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = override_get_db

    return application


@pytest_asyncio.fixture
async def client(
    test_app: FastAPI,
) -> AsyncGenerator[AsyncClient]:
    """
    Provide an asynchronous HTTP client for API integration tests.
    """

    transport = ASGITransport(
        app=test_app,
    )

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client


@pytest.fixture
def internal_api_headers() -> dict[str, str]:
    """
    Headers required by protected internal API endpoints.
    """

    return {
        "X-Internal-API-Key": "test-internal-api-key",
        "Content-Type": "application/json",
    }


@pytest.fixture
def invalid_internal_api_headers() -> dict[str, str]:
    """
    Invalid internal API credentials for authorization tests.
    """

    return {
        "X-Internal-API-Key": "invalid-api-key",
        "Content-Type": "application/json",
    }


@pytest.fixture
def verification_email_payload() -> dict[str, Any]:
    """
    Valid verification-email API request.
    """

    return {
        "recipient": {
            "email": "customer@example.com",
            "name": "Marketplace Customer",
        },
        "first_name": "Customer",
        "verification_token": "verification-token-123",
        "verification_url": (
            "http://localhost:3000/verify-email"
            "?token=verification-token-123"
        ),
        "expires_in_minutes": 30,
        "external_reference": "user-123",
        "priority": NotificationPriority.HIGH.value,
    }


@pytest.fixture
def password_reset_email_payload() -> dict[str, Any]:
    """
    Valid password-reset API request.
    """

    return {
        "recipient": {
            "email": "customer@example.com",
            "name": "Marketplace Customer",
        },
        "first_name": "Customer",
        "reset_token": "reset-token-123",
        "reset_url": (
            "http://localhost:3000/reset-password"
            "?token=reset-token-123"
        ),
        "expires_in_minutes": 20,
        "external_reference": "user-123",
        "priority": NotificationPriority.HIGH.value,
    }


@pytest.fixture
def password_changed_email_payload() -> dict[str, Any]:
    """
    Valid password-changed API request.
    """

    return {
        "recipient": {
            "email": "customer@example.com",
            "name": "Marketplace Customer",
        },
        "first_name": "Customer",
        "changed_at": datetime.now(
            UTC
        ).isoformat(),
        "ip_address": "127.0.0.1",
        "user_agent": "pytest-test-client",
        "external_reference": "user-123",
        "priority": NotificationPriority.HIGH.value,
    }


@pytest.fixture
def direct_email_payload() -> dict[str, Any]:
    """
    Valid direct-email API request.
    """

    return {
        "recipient": {
            "email": "customer@example.com",
            "name": "Marketplace Customer",
        },
        "subject": "Marketplace Test Notification",
        "body_text": "This is a test notification.",
        "body_html": (
            "<p>This is a <strong>test notification</strong>.</p>"
        ),
        "sender": {
            "email": "no-reply@marketplace.local",
            "name": "Marketplace",
        },
        "reply_to_email": "support@marketplace.local",
        "priority": NotificationPriority.NORMAL.value,
        "external_reference": "test-message-123",
        "max_retry_count": 3,
        "headers": {
            "X-Test-Notification": "true",
        },
        "metadata": {
            "source": "pytest",
        },
    }


@pytest_asyncio.fixture
async def pending_notification(
    db_session: AsyncSession,
) -> Notification:
    """
    Persist a pending notification for service and route tests.
    """

    notification = Notification(
        type=NotificationType.EMAIL,
        status=NotificationStatus.PENDING,
        priority=NotificationPriority.NORMAL,
        provider=ProviderType.CONSOLE,
        template_name=None,
        subject="Pending notification",
        recipient="customer@example.com",
        recipient_name="Marketplace Customer",
        sender="no-reply@marketplace.local",
        sender_name="Marketplace",
        body_text="Pending test notification",
        body_html="<p>Pending test notification</p>",
        template_data={},
        metadata={
            "source": "pytest",
        },
        retry_count=0,
        max_retry_count=3,
        external_reference="pending-test-123",
        is_deleted=False,
    )

    db_session.add(notification)
    await db_session.flush()
    await db_session.refresh(notification)

    return notification


@pytest_asyncio.fixture
async def failed_notification(
    db_session: AsyncSession,
) -> Notification:
    """
    Persist a failed notification that can be used in retry tests.
    """

    notification = Notification(
        type=NotificationType.EMAIL,
        status=NotificationStatus.FAILED,
        priority=NotificationPriority.HIGH,
        provider=ProviderType.CONSOLE,
        template_name=None,
        subject="Failed notification",
        recipient="customer@example.com",
        recipient_name="Marketplace Customer",
        sender="no-reply@marketplace.local",
        sender_name="Marketplace",
        body_text="Failed test notification",
        body_html="<p>Failed test notification</p>",
        template_data={},
        metadata={
            "source": "pytest",
        },
        retry_count=1,
        max_retry_count=3,
        error_message="Simulated provider failure",
        failed_at=datetime.now(UTC),
        external_reference="failed-test-123",
        is_deleted=False,
    )

    db_session.add(notification)
    await db_session.flush()
    await db_session.refresh(notification)

    return notification


@pytest_asyncio.fixture
async def sent_notification(
    db_session: AsyncSession,
) -> Notification:
    """
    Persist a sent notification for read and state-validation tests.
    """

    notification = Notification(
        type=NotificationType.EMAIL,
        status=NotificationStatus.SENT,
        priority=NotificationPriority.NORMAL,
        provider=ProviderType.CONSOLE,
        template_name=None,
        subject="Sent notification",
        recipient="customer@example.com",
        recipient_name="Marketplace Customer",
        sender="no-reply@marketplace.local",
        sender_name="Marketplace",
        body_text="Sent test notification",
        body_html="<p>Sent test notification</p>",
        template_data={},
        metadata={
            "source": "pytest",
        },
        retry_count=0,
        max_retry_count=3,
        provider_message_id=f"mock-{uuid4()}",
        sent_at=datetime.now(UTC),
        external_reference="sent-test-123",
        is_deleted=False,
    )

    db_session.add(notification)
    await db_session.flush()
    await db_session.refresh(notification)

    return notification
