from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: UUID
    roles: frozenset[str]
    scopes: frozenset[str]
    claims: dict

    def has_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))


class JWKSDecoder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = PyJWKClient(
            settings.jwt_jwks_url,
            cache_keys=True,
            lifespan=settings.jwks_cache_seconds,
        )

    def decode(self, token: str) -> dict:
        header = jwt.get_unverified_header(token)
        if not header.get("kid"):
            raise jwt.InvalidTokenError("Missing kid")
        if header.get("alg") not in self.settings.jwt_algorithms:
            raise jwt.InvalidAlgorithmError("Algorithm not allowed")
        key = self.client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            key.key,
            algorithms=self.settings.jwt_algorithms,
            issuer=self.settings.jwt_issuer,
            audience=self.settings.jwt_audience,
            options={
                "require": ["sub", "iss", "aud", "exp"],
                "verify_exp": True,
                "verify_nbf": True,
            },
        )


@lru_cache
def get_decoder() -> JWKSDecoder:
    return JWKSDecoder(get_settings())


def _claim_set(value: object) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset(value.split())
    if isinstance(value, list):
        return frozenset(str(item) for item in value)
    return frozenset()


async def current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    decoder: JWKSDecoder = Depends(get_decoder),
) -> Principal:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token is required")
    try:
        claims = decoder.decode(credentials.credentials)
        subject = UUID(str(claims["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid access token"
        ) from exc
    return Principal(
        subject=subject,
        roles=_claim_set(claims.get("roles") or claims.get("role")),
        scopes=_claim_set(claims.get("scope") or claims.get("scopes")),
        claims=claims,
    )


def require_roles(*roles: str):
    async def dependency(
        principal: Principal = Depends(current_principal),
    ) -> Principal:
        if not principal.has_role(*roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal

    return dependency


def require_scope(scope: str):
    async def dependency(
        principal: Principal = Depends(current_principal),
    ) -> Principal:
        if scope not in principal.scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Required scope: {scope}")
        return principal

    return dependency
