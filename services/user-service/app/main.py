from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.exceptions import register_exception_handlers
from app.middleware import CorrelationIdMiddleware
from app.routes import (
    addresses_router,
    health_router,
    preferences_router,
    privacy_router,
    profiles_router,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    app = FastAPI(
        title="Marketplace User Service",
        version=resolved_settings.version,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url="/redoc" if resolved_settings.docs_enabled else None,
        openapi_url="/openapi.json" if resolved_settings.docs_enabled else None,
    )
    app.state.settings = resolved_settings
    app.dependency_overrides[get_settings] = lambda: resolved_settings
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    for router in (
        health_router,
        profiles_router,
        addresses_router,
        preferences_router,
        privacy_router,
    ):
        app.include_router(router, prefix=resolved_settings.api_v1_prefix)
    return app


app = create_app()
