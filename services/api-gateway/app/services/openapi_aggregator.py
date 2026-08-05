import asyncio
import copy
import time

import httpx

from app.config import get_settings
from app.services.routing import resolve

_CACHE_TTL_SECONDS = 30.0
_cache: dict | None = None
_cache_at: float = 0.0
_cache_lock = asyncio.Lock()

# Keys here double as the "service name" used to namespace component schemas
# (see namespace_schema) and must match the `upstream_setting` values in
# app/services/routing.py, which are always "<name>_service_url".
SERVICE_BASE_URL_SETTINGS = {
    "auth": "auth_service_url",
    "user": "user_service_url",
    "product": "product_service_url",
    "inventory": "inventory_service_url",
    "cart": "cart_service_url",
    "order": "order_service_url",
    "payment": "payment_service_url",
    "shipping": "shipping_service_url",
}


def namespace_schema(service_name: str, schema: dict) -> dict:
    """Deep-copy `schema`, prefixing every component schema name — and every
    $ref pointing at one — with `service_name`.

    Every service independently generates its own "HTTPValidationError" /
    "MessageResponse" / etc. from the same FastAPI/Pydantic conventions.
    Merging several services' schemas without this would silently let one
    service's definition clobber another's under the same key whenever
    their actual shapes differ, corrupting "Try it out" request/response
    rendering for whichever one lost. `securitySchemes` is untouched: every
    service defines the same `HTTPBearer` scheme, and keeping the shared
    name is what lets Swagger UI's single "Authorize" button apply to every
    aggregated operation at once instead of one per service.
    """
    schema = copy.deepcopy(schema)

    def rewrite(node: object) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                original = ref.removeprefix("#/components/schemas/")
                node["$ref"] = f"#/components/schemas/{service_name}_{original}"
            for value in node.values():
                rewrite(value)
        elif isinstance(node, list):
            for item in node:
                rewrite(item)

    rewrite(schema)

    schemas = schema.get("components", {}).get("schemas", {})
    schema.setdefault("components", {})["schemas"] = {
        f"{service_name}_{name}": definition for name, definition in schemas.items()
    }
    return schema


def filter_paths_for_service(service_name: str, paths: dict) -> dict:
    """Keep only the paths the gateway's own allowlist (app/services/routing.py)
    actually routes to this service.

    A service's real openapi.json also documents its internal-only routes,
    its own /health, /ready, /docs, etc. — none of those are proxied, and
    this drops them the same way the live proxy route would 404 them, so
    the aggregated docs can never show a "testable" endpoint that the
    gateway would actually reject.
    """
    upstream_setting = SERVICE_BASE_URL_SETTINGS[service_name]
    return {
        path: path_item
        for path, path_item in paths.items()
        if (route := resolve(path)) is not None
        and route.upstream_setting == upstream_setting
    }


async def _fetch_service_schema(
    client: httpx.AsyncClient, service_name: str, base_url: str
) -> tuple[str, dict | None]:
    try:
        response = await client.get(f"{base_url}/openapi.json", timeout=3.0)
        response.raise_for_status()
        return service_name, response.json()
    except httpx.HTTPError:
        return service_name, None


async def _build() -> dict:
    settings = get_settings()
    services = {
        name: getattr(settings, setting)
        for name, setting in SERVICE_BASE_URL_SETTINGS.items()
    }

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(
                _fetch_service_schema(client, name, base_url)
                for name, base_url in services.items()
            )
        )

    paths: dict = {}
    component_schemas: dict = {}
    security_schemes: dict = {}
    unreachable: list[str] = []

    for service_name, raw_schema in results:
        if raw_schema is None:
            unreachable.append(service_name)
            continue
        namespaced = namespace_schema(service_name, raw_schema)
        paths.update(
            filter_paths_for_service(service_name, namespaced.get("paths", {}))
        )
        components = namespaced.get("components", {})
        component_schemas.update(components.get("schemas", {}))
        security_schemes.update(components.get("securitySchemes", {}))

    description = (
        "Aggregated, testable view of every route this gateway actually "
        "proxies (not a static doc — pulled live from each service's own "
        "/openapi.json on each load, filtered through the same allowlist "
        "the proxy route enforces at app/services/routing.py). "
        "'Try it out' below sends requests to this gateway on its own "
        "origin, exactly as a real client would — not directly to the "
        "downstream service. See docs/route-allowlist.md for what's "
        "excluded and why (internal-only callbacks, service-token "
        "exchange, health probes)."
    )
    if unreachable:
        description += (
            "\n\n⚠️ Unreachable when this was built: "
            f"{', '.join(sorted(unreachable))} — their routes are omitted "
            "below (not necessarily blocked by the allowlist; refresh with "
            "`?refresh=true` once they're back up)."
        )

    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"{settings.app_name} (aggregated)",
            "version": settings.app_version,
            "description": description,
        },
        "paths": dict(sorted(paths.items())),
        "components": {
            "schemas": component_schemas,
            "securitySchemes": security_schemes,
        },
    }


async def build_aggregated_openapi(force_refresh: bool = False) -> dict:
    global _cache, _cache_at
    now = time.monotonic()
    cache_fresh = _cache is not None and (now - _cache_at) < _CACHE_TTL_SECONDS
    if not force_refresh and cache_fresh:
        return _cache
    async with _cache_lock:
        now = time.monotonic()
        if (
            not force_refresh
            and _cache is not None
            and (now - _cache_at) < _CACHE_TTL_SECONDS
        ):
            return _cache
        schema = await _build()
        _cache = schema
        _cache_at = now
        return schema
