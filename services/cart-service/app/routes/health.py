from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok", service=settings.app_name, version=settings.app_version
    )


@router.get("/ready", response_model=HealthResponse, tags=["health"])
async def ready(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    await session.execute(text("SELECT 1"))
    settings = get_settings()
    return HealthResponse(
        status="ready", service=settings.app_name, version=settings.app_version
    )
