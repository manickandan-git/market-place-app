from fastapi import APIRouter, Query
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import get_settings
from app.services.openapi_aggregator import build_aggregated_openapi

# include_in_schema doesn't apply here (these routes serve the schema
# itself), but keeping this its own router mirrors the health/proxy split.
router = APIRouter()


@router.get("/openapi.json", include_in_schema=False)
async def openapi_json(
    refresh: bool = Query(default=False, description="Bypass the 30s cache"),
) -> JSONResponse:
    schema = await build_aggregated_openapi(force_refresh=refresh)
    return JSONResponse(schema)


@router.get("/docs", include_in_schema=False)
async def swagger_ui() -> HTMLResponse:
    settings = get_settings()
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{settings.app_name} — Swagger UI",
    )
