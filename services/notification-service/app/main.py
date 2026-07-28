from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import (
    check_database_connection,
    close_database_connections,
)
from app.email_service import EmailService, EmailServiceError
from app.routes import router as notification_router
from app.schemas import (
    DependencyHealth,
    HealthResponse,
    ReadinessResponse,
)

settings = get_settings()

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """
    Configure application-wide logging.
    """

    logging.basicConfig(
        level=getattr(
            logging,
            settings.log_level.upper(),
            logging.INFO,
        ),
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(processName)s | %(name)s | %(message)s"
        ),
    )


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """
    Manage application startup and shutdown.

    Startup validates critical configuration and checks whether the database
    can be reached. Shutdown disposes SQLAlchemy connection pools.
    """

    logger.info(
        "Starting Notification Service",
        extra={
            "application": settings.app_name,
            "environment": settings.app_env,
            "version": settings.app_version,
            "email_provider": str(settings.email_provider),
        },
    )

    database_healthy = await check_database_connection()

    if database_healthy:
        logger.info("Database connection verified")
    else:
        logger.warning(
            "Database connection could not be verified during startup"
        )

    yield

    logger.info("Stopping Notification Service")

    await close_database_connections()

    logger.info(
        "Notification Service shutdown completed"
    )


def create_application() -> FastAPI:
    """
    Create and configure the FastAPI application.
    """

    application = FastAPI(
        title=settings.app_name,
        description=(
            "Marketplace Notification Service for transactional email, "
            "delivery tracking, retries, and notification operations."
        ),
        version=settings.app_version,
        debug=settings.app_env.lower() == "development",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    configure_cors(application)
    register_routers(application)
    register_exception_handlers(application)
    register_service_routes(application)

    return application


def register_service_routes(
    application: FastAPI,
) -> None:
    """
    Register basic service and health endpoints.
    """

    @application.get(
        "/",
        tags=["Service"],
    )
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
            "status": "running",
            "documentation": "/docs",
        }

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
    )
    async def health_check() -> HealthResponse:
        return HealthResponse(
            status="healthy",
            service=settings.app_name,
            version=settings.app_version,
            timestamp=datetime.now(UTC),
        )

    @application.get(
        "/ready",
        response_model=ReadinessResponse,
        tags=["Health"],
    )
    async def readiness_check() -> ReadinessResponse:
        database_healthy = await check_database_connection()

        provider_healthy = False
        provider_name = str(settings.email_provider)

        try:
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                service = EmailService(db)

                provider_name = (
                    service.provider.provider_type.value
                )

                provider_healthy = (
                    service.provider.health_check()
                )

        except Exception:
            logger.exception(
                "Email provider readiness check failed"
            )

        dependencies = {
            "database": DependencyHealth(
                status=(
                    "healthy"
                    if database_healthy
                    else "unhealthy"
                ),
                detail=(
                    "PostgreSQL connection successful"
                    if database_healthy
                    else "PostgreSQL connection failed"
                ),
            ),
            "email_provider": DependencyHealth(
                status=(
                    "healthy"
                    if provider_healthy
                    else "unhealthy"
                ),
                detail=(
                    f"Provider '{provider_name}' is available"
                    if provider_healthy
                    else f"Provider '{provider_name}' is unavailable"
                ),
            ),
        }

        is_ready = (
            database_healthy
            and provider_healthy
        )

        response = ReadinessResponse(
            status=(
                "ready"
                if is_ready
                else "not_ready"
            ),
            service=settings.app_name,
            version=settings.app_version,
            timestamp=datetime.now(UTC),
            dependencies=dependencies,
        )

        if not is_ready:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=response.model_dump(
                    mode="json"
                ),
            )

        return response


def configure_cors(application: FastAPI) -> None:
    """
    Configure Cross-Origin Resource Sharing.

    Notification endpoints are primarily intended for service-to-service
    communication. Restrict allowed origins in production.
    """

    allowed_origins = getattr(
        settings,
        "cors_allowed_origins",
        [
            "http://localhost:3000",
            "http://localhost:5173",
        ],
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=[
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Internal-API-Key",
            "X-Request-ID",
        ],
    )


def register_routers(application: FastAPI) -> None:
    """
    Register API routers.
    """

    application.include_router(
        notification_router,
        prefix="/api/v1",
    )


def register_exception_handlers(
    application: FastAPI,
) -> None:
    """
    Register consistent application exception responses.
    """

    @application.exception_handler(
        EmailServiceError
    )
    async def handle_email_service_error(
        request: Request,
        exc: EmailServiceError,
    ) -> JSONResponse:
        logger.warning(
            "Email service request failed",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error": str(exc),
            },
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": str(exc),
                "error_type": exc.__class__.__name__,
            },
        )

    @application.exception_handler(
        SQLAlchemyError
    )
    async def handle_database_error(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:
        logger.exception(
            "Database operation failed",
            extra={
                "path": request.url.path,
                "method": request.method,
            },
        )

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": (
                    "The notification database is temporarily unavailable"
                ),
                "error_type": "DatabaseError",
            },
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled application error",
            extra={
                "path": request.url.path,
                "method": request.method,
            },
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An unexpected server error occurred",
                "error_type": "InternalServerError",
            },
        )


app = create_application()

