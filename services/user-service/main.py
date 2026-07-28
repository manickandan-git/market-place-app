import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.database import (
    check_database_connection,
    close_database_connection,
)

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await close_database_connection()

    app = FastAPI(
        title="Marketplace User Service",
        version="0.1.0",
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url="/redoc" if resolved_settings.docs_enabled else None,
        openapi_url="/openapi.json" if resolved_settings.docs_enabled else None,
        lifespan=lifespan,
    )

    app.state.settings = resolved_settings

    health_router = APIRouter(
        prefix="/health",
        tags=["health"],
    )

    @health_router.get("/live", summary="Check process liveness")
    async def liveness() -> dict[str, str]:
        return {
            "status": "ok",
            "service": resolved_settings.service_name,
            "environment": resolved_settings.environment,
        }

    @health_router.get(
        "/ready",
        summary="Check service readiness",
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "description": "PostgreSQL is unavailable",
            }
        },
    )
    async def readiness() -> dict[str, str] | JSONResponse:
        try:
            await check_database_connection()
        except Exception:
            logger.exception("Database readiness check failed")

            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not_ready",
                    "database": "unavailable",
                },
            )

        return {
            "status": "ready",
            "database": "available",
        }

    app.include_router(
        health_router,
        prefix=resolved_settings.api_v1_prefix,
    )

    return app


app = create_app()