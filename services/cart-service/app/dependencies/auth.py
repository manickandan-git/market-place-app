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
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = PyJWKClient(
            settings.jwt_jwks_url,
            cache_keys=True,
            lifespan=settings.jwks_cache_seconds,
        )

    def decode(self, token: str) -> dict:
        header = jwt.get_unverified_header(token)
        if not header.get("kid"):
            raise jwt.InvalidTokenError("Token header is missing kid")
        if header.get("alg") not in self.settings.jwt_algorithms:
            raise jwt.InvalidAlgorithmError("Token algorithm is not allowed")
        signing_key = self.client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
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


def _as_set(value: object) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset(value.split())
    if isinstance(value, list):
        return frozenset(str(item) for item in value)
    return frozenset()


async def get_optional_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    decoder: JWKSDecoder = Depends(get_decoder),
) -> Principal | None:
    if credentials is None:
        return None
    try:
        claims = decoder.decode(credentials.credentials)
        subject = UUID(str(claims["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        ) from exc
    return Principal(
        subject=subject,
        roles=_as_set(claims.get("roles") or claims.get("role")),
        scopes=_as_set(claims.get("scope") or claims.get("scopes")),
        claims=claims,
    )


async def get_current_principal(
    principal: Principal | None = Depends(get_optional_principal),
) -> Principal:
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
        )
    return principal


def require_scope(required_scope: str):
    async def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if required_scope not in principal.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required scope: {required_scope}",
            )
        return principal

    return dependency
