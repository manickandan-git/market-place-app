from fastapi import Request

from app.services.proxy_service import ProxyService
from app.services.token_verifier import TokenVerifier


def get_proxy_service(request: Request) -> ProxyService:
    return request.app.state.proxy_service


def get_token_verifier(request: Request) -> TokenVerifier:
    return request.app.state.token_verifier
