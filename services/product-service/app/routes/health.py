from fastapi import APIRouter

from app import __version__
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        service="product-service",
        status="healthy",
        version=__version__,
    )


@router.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    return HealthResponse(
        service="product-service",
        status="ready",
        version=__version__,
    )

