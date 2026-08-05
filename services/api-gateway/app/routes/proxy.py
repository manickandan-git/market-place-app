from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.config import get_settings
from app.exceptions import ServiceError
from app.routes.dependencies import get_proxy_service, get_token_verifier
from app.services.proxy_service import ProxyService
from app.services.routing import resolve
from app.services.token_verifier import TokenVerifier

router = APIRouter()

ProxyDep = Annotated[ProxyService, Depends(get_proxy_service)]
TokenVerifierDep = Annotated[TokenVerifier, Depends(get_token_verifier)]

BEARER_PREFIX = "bearer "


@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def proxy(
    full_path: str,
    request: Request,
    proxy_service: ProxyDep,
    token_verifier: TokenVerifierDep,
) -> Response:
    route = resolve(request.url.path)
    if route is None:
        raise ServiceError(
            404,
            "not_found",
            "No route matches this path",
        )

    # Edge-level authentication only (signature/exp/iss/aud) — see
    # TokenVerifier's docstring. A request with no Authorization header is
    # passed through untouched: many allowlisted routes are intentionally
    # unauthenticated, and only the owning service knows which ones.
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith(BEARER_PREFIX):
        token_verifier.verify(authorization[len(BEARER_PREFIX) :])

    upstream_base = getattr(get_settings(), route.upstream_setting)
    return await proxy_service.forward(request, upstream_base, route.upstream_setting)
