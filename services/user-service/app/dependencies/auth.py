from dataclasses import dataclass
from uuid import UUID

import jwt
from anyio import to_thread
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes
from jwt import PyJWKClient

from app.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    roles: frozenset[str]
    scopes: frozenset[str]

    def has_role(self, role: str) -> bool:
        return role in self.roles


def _string_set(value: object) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset(value.split())
    if isinstance(value, list):
        return frozenset(str(item) for item in value)
    return frozenset()


async def get_current_user(
    security_scopes: SecurityScopes,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required"
        )
    try:
        jwks_client = PyJWKClient(settings.identity_jwks_url)
        signing_key = await to_thread.run_sync(
            jwks_client.get_signing_key_from_jwt,
            credentials.credentials,
        )
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=settings.jwt_algorithms,
            audience=settings.identity_audience,
            issuer=settings.identity_issuer,
        )
        user = CurrentUser(
            user_id=UUID(claims["sub"]),
            roles=_string_set(claims.get("roles")),
            scopes=_string_set(claims.get("scope", claims.get("scp"))),
        )
    except (KeyError, ValueError, jwt.PyJWTError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from exc
    missing = set(security_scopes.scopes) - user.scopes
    if missing:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient scope")
    return user


async def require_seller(user: CurrentUser = Security(get_current_user)) -> CurrentUser:
    if not user.has_role("seller"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller role required")
    return user
