from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models in the Notification Service.
    """

    pass


# NullPool is required, not just a safe default: this module is imported by
# both the FastAPI app (one persistent event loop for the process lifetime)
# and the Celery worker (tasks.py runs `asyncio.run(...)` once per task,
# creating a brand-new event loop every time). asyncpg connections are bound
# to the event loop that created them. A pooled connection checked out in a
# later, different event loop crashes pool_pre_ping's liveness check with
# "got Future ... attached to a different loop". NullPool opens a fresh
# connection per checkout instead of reusing one across loop boundaries.
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    poolclass=NullPool,
)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
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