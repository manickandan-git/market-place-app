from __future__ import annotations

import time

import httpx

from app.config import Settings
from app.exceptions import ServiceError


class AuthClient:
    """Fetches and caches a service-token (client-credentials) bearer
    token carrying inventory:checkout + inventory:commit + cart:checkout,
    for calls order-service makes with its own authority: Inventory's
    checkout reservation-create call during checkout itself, Inventory's
    commit/release endpoints when the caller isn't the buyer (e.g. Payment
    Service's webhook calling payment_authorized/payment_failed), and
    Cart's checked-out callback after placing an order."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def service_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._expires_at:
            return self._token

        owns = self.client is None
        client = self.client or httpx.AsyncClient(
            base_url=self.settings.auth_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        try:
            response = await client.post(
                "/api/v1/auth/service-token",
                json={
                    "client_id": self.settings.inventory_expire_client_id,
                    "client_secret": self.settings.inventory_expire_client_secret,
                },
            )
        except httpx.RequestError as exc:
            raise ServiceError(
                503, "auth_unavailable", "Auth Service is unavailable"
            ) from exc
        finally:
            if owns:
                await client.aclose()
        if response.status_code >= 400:
            raise ServiceError(
                502, "service_token_failed", "Could not obtain a service token"
            )
        data = response.json()
        self._token = data["access_token"]
        # Refresh a bit early so a call never races a just-expired token.
        self._expires_at = now + max(int(data["expires_in"]) - 30, 0)
        return self._token
