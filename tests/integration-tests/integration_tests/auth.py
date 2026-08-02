from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt

from integration_tests.clients import MarketplaceClients
from integration_tests.config import Settings


@dataclass(frozen=True)
class Persona:
    name: str
    token: str
    claims: dict[str, Any]

    @property
    def subject(self) -> str:
        return str(self.claims["sub"])


def unverified_claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={
            "verify_signature": False,
            "verify_exp": False,
            "verify_aud": False,
        },
    )


async def resolve_token(
    *,
    name: str,
    supplied_token: str | None,
    email: str | None,
    password: str | None,
    clients: MarketplaceClients,
    settings: Settings,
) -> Persona:
    token = supplied_token.strip() if supplied_token else None
    if not token:
        if not email or not password:
            raise RuntimeError(
                f"Configure {name.upper()}_ACCESS_TOKEN or both the {name.upper()} "
                "email and password values in .env.integration"
            )
        payload = {
            settings.auth_login_email_field: email,
            settings.auth_login_password_field: password,
        }
        result = await clients.auth.json(
            "POST",
            settings.auth_login_path,
            json=payload,
            expected=200,
        )
        try:
            token = str(result[settings.auth_login_token_field])
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                "Auth login response did not contain "
                f"'{settings.auth_login_token_field}'. Response: {result!r}"
            ) from exc
    claims = unverified_claims(token)
    if not claims.get("sub"):
        raise RuntimeError(f"The {name} token does not contain a sub claim")
    return Persona(name=name, token=token, claims=claims)

