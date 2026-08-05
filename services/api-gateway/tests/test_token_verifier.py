import jwt
import pytest

from app.config import Settings
from app.exceptions import ServiceError
from app.services.token_verifier import TokenVerifier


def _verifier() -> TokenVerifier:
    settings = Settings(jwt_jwks_url="http://localhost:8001/.well-known/jwks.json")
    return TokenVerifier(settings)


# All three cases below are rejected before TokenVerifier ever needs to
# reach out over the network for the JWKS — a garbage string fails at
# jwt.get_unverified_header, a missing `kid` fails our own explicit check,
# and a disallowed algorithm fails before get_signing_key_from_jwt is
# called. That's what makes these fast, deterministic unit tests instead
# of needing a live auth-service or a mocked JWKS endpoint.


def test_garbage_token_is_rejected():
    verifier = _verifier()
    with pytest.raises(ServiceError) as exc_info:
        verifier.verify("not-a-real-jwt")
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "invalid_token"


def test_token_missing_kid_is_rejected():
    verifier = _verifier()
    token = jwt.encode({"sub": "abc"}, "a" * 32, algorithm="HS256")
    with pytest.raises(ServiceError) as exc_info:
        verifier.verify(token)
    assert exc_info.value.status_code == 401


def test_disallowed_algorithm_is_rejected():
    verifier = _verifier()
    token = jwt.encode(
        {"sub": "abc"}, "a" * 32, algorithm="HS256", headers={"kid": "some-key"}
    )
    with pytest.raises(ServiceError) as exc_info:
        verifier.verify(token)
    assert exc_info.value.status_code == 401
