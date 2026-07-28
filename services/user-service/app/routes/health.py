from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "environment": settings.environment,
    }


@router.get("/ready")
async def readiness() -> dict[str, str]:
    # Lightweight by design for local bootstrapping. Use /ready/database for a DB probe.
    return {"status": "ready"}


@router.get("/ready/database")
async def database_readiness(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
