from __future__ import annotations

import jwt
import pytest
from jwt import PyJWKClient

from integration_tests.helpers import roles, scopes

pytestmark = pytest.mark.integration


def _verify_token(token: str, settings) -> dict:
    header = jwt.get_unverified_header(token)
    assert header.get("kid"), "Identity token must have a kid header"
    assert header.get("alg") in settings.jwt_algorithms
    jwks_url = settings.url(settings.auth_service_url, settings.auth_jwks_path)
    signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=settings.jwt_algorithms,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={"require": ["sub", "iss", "aud", "exp"]},
    )


def test_buyer_token_matches_jwks_contract(buyer, settings):
    claims = _verify_token(buyer.token, settings)
    assert claims["sub"] == buyer.subject
    assert "buyer" in roles(claims)


def test_seller_token_matches_jwks_contract(seller_a, settings):
    claims = _verify_token(seller_a.token, settings)
    assert "seller" in roles(claims)


def test_inventory_sync_token_scope(inventory_sync, settings):
    claims = _verify_token(inventory_sync.token, settings)
    assert "inventory:sync" in scopes(claims)

