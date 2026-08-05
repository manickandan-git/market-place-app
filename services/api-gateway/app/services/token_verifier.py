import jwt
from jwt import PyJWKClient

from app.config import Settings
from app.exceptions import ServiceError


class TokenVerifier:
    """Fail-fast, edge-level JWT check performed once before proxying.

    This is centralized *authentication* only — signature, expiry, issuer,
    and audience via the same JWKS every service already trusts — not
    authorization. It does not replace any downstream service's own JWT
    verification plus role/scope/ownership checks, which still run
    unchanged on every request that reaches them (see the parent
    conversation / docs/route-allowlist.md for why fine-grained
    authorization has to stay there: only the owning service has the
    resource-ownership data to do it correctly). The only thing this saves
    is a wasted network hop to a service that would reject the token
    anyway.

    A request with no `Authorization` header at all is never touched here:
    many allowlisted routes (login, register, public catalog reads) are
    intentionally unauthenticated, and only the owning service knows
    whether a given route requires a token. `POST /api/v1/webhooks/stripe`
    is exempted the same way — Stripe never sends a bearer token, so it
    naturally never reaches this check.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks_client = PyJWKClient(
            settings.jwt_jwks_url,
            cache_keys=True,
            lifespan=settings.jwks_cache_seconds,
        )

    def verify(self, token: str) -> None:
        try:
            header = jwt.get_unverified_header(token)
            if not header.get("kid"):
                raise jwt.InvalidTokenError("Token header is missing kid")
            if header.get("alg") not in self._settings.jwt_algorithms:
                raise jwt.InvalidAlgorithmError("Token algorithm is not allowed")
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            jwt.decode(
                token,
                signing_key.key,
                algorithms=self._settings.jwt_algorithms,
                issuer=self._settings.jwt_issuer,
                audience=self._settings.jwt_audience,
                options={
                    "require": ["sub", "iss", "aud", "exp"],
                    "verify_exp": True,
                    "verify_nbf": True,
                },
            )
        except jwt.PyJWTError as exc:
            raise ServiceError(
                401, "invalid_token", "Invalid or expired access token"
            ) from exc
