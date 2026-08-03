import os
from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://inventory:inventory@localhost:5435/inventory_service",
)

from app.models import Base  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw) -> str:
    # audit_logs/outbox_events use postgres JSONB in production; sqlite (used
    # only here, for fast in-process tests) has no JSONB type, so render it
    # as plain JSON instead. Test-only — does not affect the real schema.
    return "JSON"


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()
