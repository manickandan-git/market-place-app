from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class NotificationClient:
    """
    Outbound client for the Notification Service.

    Every call is best-effort: the Notification Service being unreachable
    or erroring must never block or fail an auth flow (registration, login,
    password reset). Failures are logged and swallowed, never raised.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()

        self._base_url = (
            base_url or settings.notification_service_url
        ).rstrip("/")

        self._api_key = (
            api_key or settings.notification_service_api_key
        )

        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.notification_service_timeout_seconds
        )

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> None:
        url = f"{self._base_url}/api/v1/notifications{path}"

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout
            ) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "X-Internal-API-Key": self._api_key,
                    },
                )

                response.raise_for_status()

        except httpx.HTTPError as exc:
            logger.warning(
                "Notification Service request failed",
                extra={
                    "url": url,
                    "error": str(exc),
                },
            )

    async def send_verification_email(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        first_name: str,
        verification_token: str,
        expires_in_minutes: int,
        user_id: UUID | None = None,
        external_reference: str | None = None,
    ) -> None:
        await self._post(
            "/email/verification",
            {
                "recipient": {
                    "email": recipient_email,
                    "name": recipient_name,
                },
                "user_id": str(user_id) if user_id else None,
                "first_name": first_name,
                "verification_token": verification_token,
                "expires_in_minutes": expires_in_minutes,
                "external_reference": external_reference,
            },
        )

    async def send_password_reset_email(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        first_name: str,
        reset_token: str,
        expires_in_minutes: int,
        user_id: UUID | None = None,
        external_reference: str | None = None,
    ) -> None:
        await self._post(
            "/email/password-reset",
            {
                "recipient": {
                    "email": recipient_email,
                    "name": recipient_name,
                },
                "user_id": str(user_id) if user_id else None,
                "first_name": first_name,
                "reset_token": reset_token,
                "expires_in_minutes": expires_in_minutes,
                "external_reference": external_reference,
            },
        )

    async def send_password_changed_email(
        self,
        *,
        recipient_email: str,
        recipient_name: str,
        first_name: str,
        changed_at: datetime,
        ip_address: str | None = None,
        user_id: UUID | None = None,
        external_reference: str | None = None,
    ) -> None:
        await self._post(
            "/email/password-changed",
            {
                "recipient": {
                    "email": recipient_email,
                    "name": recipient_name,
                },
                "user_id": str(user_id) if user_id else None,
                "first_name": first_name,
                "changed_at": changed_at.isoformat(),
                "ip_address": ip_address,
                "external_reference": external_reference,
            },
        )


_notification_client: NotificationClient | None = None


def get_notification_client() -> NotificationClient:
    """
    Return a shared NotificationClient instance.
    """

    global _notification_client

    if _notification_client is None:
        _notification_client = NotificationClient()

    return _notification_client
