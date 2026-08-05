from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.exceptions import register_exception_handlers
from app.middleware import CorrelationIdMiddleware
from app.routes import docs_router, health_router, proxy_router
from app.services.proxy_service import ProxyService
from app.services.token_verifier import TokenVerifier

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = httpx.AsyncClient()
    app.state.proxy_service = ProxyService(client, settings)
    app.state.token_verifier = TokenVerifier(settings)
    yield
    await client.aclose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
    # FastAPI's built-in /openapi.json + /docs routes call app.openapi()
    # synchronously — incompatible with the async downstream fetches
    # aggregation needs. Disabled here in favor of the async routes in
    # app/routes/docs.py, which serve the same URLs.
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# health_router and docs_router must be included before proxy_router: the
# catch-all proxy route (`/{full_path:path}`) would otherwise shadow
# /health, /ready, /docs, and /openapi.json — FastAPI matches routes in
# registration order.
app.include_router(health_router)
app.include_router(docs_router)
app.include_router(proxy_router)
register_exception_handlers(app)
