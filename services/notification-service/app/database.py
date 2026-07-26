from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models in the Notification Service.
    """

    pass


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_recycle=1800,
)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI database dependency.

    Creates one asynchronous SQLAlchemy session for each request.

    The session is:

    - committed explicitly by the service or route
    - rolled back automatically when an exception occurs
    - closed after the request finishes
    """

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """
    Verify that the Notification Service can connect to the database.

    This function is intended for readiness checks.
    """

    from sqlalchemy import text

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        return True
    except Exception:
        return False


async def close_database_connections() -> None:
    """
    Dispose of all SQLAlchemy connection pools.

    Call this function when the application shuts down.
    """

    await engine.dispose()