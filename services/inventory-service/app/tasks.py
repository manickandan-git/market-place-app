from __future__ import annotations

import asyncio

import httpx

from app.celery_app import celery_app
from app.config import get_settings
from app.services.auth_client import AuthClient

settings = get_settings()
auth_client = AuthClient(settings)


@celery_app.task(name="app.tasks.expire_reservations")
def expire_reservations() -> dict:
    return asyncio.run(_expire_reservations())


async def _expire_reservations() -> dict:
    token = await auth_client.service_token()
    async with httpx.AsyncClient(base_url=settings.inventory_service_url) as client:
        resp = await client.post(
            f"{settings.api_prefix}/internal/reservations/expire",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()
