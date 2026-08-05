import asyncio

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings

router = APIRouter()


@router.get("/health", tags=["health"])
async def health() -> JSONResponse:
    settings = get_settings()
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
        },
    )


@router.get("/ready", tags=["health"])
async def ready() -> JSONResponse:
    """Liveness of the gateway itself plus a best-effort fan-out ping of
    every allowlisted upstream's own /health. This is the gateway's
    internal readiness probe (for orchestration), not a public route it
    proxies — it never appears in the routing table in services/routing.py.
    """
    settings = get_settings()
    # Every service exposes bare `/health` except user-service, which
    # mounts its health router under `/api/v1` too (an inconsistency with
    # the convention documented in the root CLAUDE.md, discovered by
    # actually curling each service rather than assuming uniformity).
    upstreams = {
        "auth": (settings.auth_service_url, "/health"),
        "user": (settings.user_service_url, "/api/v1/health/live"),
        "product": (settings.product_service_url, "/health"),
        "inventory": (settings.inventory_service_url, "/health"),
        "cart": (settings.cart_service_url, "/health"),
        "order": (settings.order_service_url, "/health"),
        "payment": (settings.payment_service_url, "/health"),
        "shipping": (settings.shipping_service_url, "/health"),
    }

    async def check(name: str, base_url: str, health_path: str) -> tuple[str, bool]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{base_url}{health_path}")
                return name, response.status_code == 200
        except httpx.HTTPError:
            return name, False

    results = dict(
        await asyncio.gather(
            *(
                check(name, base_url, health_path)
                for name, (base_url, health_path) in upstreams.items()
            )
        )
    )
    unhealthy = [name for name, healthy in results.items() if not healthy]

    return JSONResponse(
        status_code=200 if not unhealthy else 503,
        content={
            "status": "ready" if not unhealthy else "degraded",
            "service": settings.app_name,
            "version": settings.app_version,
            "upstreams": results,
        },
    )
