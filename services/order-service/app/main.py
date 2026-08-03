from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.exceptions import register_exception_handlers
from app.middleware import CorrelationIdMiddleware
from app.routes import health_router, router

settings = get_settings()
app = FastAPI(
    title=settings.app_name, version=settings.app_version, debug=settings.debug
)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(router, prefix=settings.api_prefix)
register_exception_handlers(app)
