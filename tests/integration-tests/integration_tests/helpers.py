from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import httpx


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


async def wait_until_healthy(
    url: str,
    *,
    timeout_seconds: float,
    verify: bool,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no response"
    async with httpx.AsyncClient(timeout=5, verify=verify) as client:
        while time.monotonic() < deadline:
            try:
                response = await client.get(url)
                if 200 <= response.status_code < 300:
                    return
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            await asyncio.sleep(1)
    raise TimeoutError(f"Service did not become healthy at {url}: {last_error}")


def roles(claims: dict) -> set[str]:
    value = claims.get("roles") or claims.get("role") or []
    if isinstance(value, str):
        return set(value.split())
    return {str(item) for item in value}


def scopes(claims: dict) -> set[str]:
    value = claims.get("scope") or claims.get("scopes") or []
    if isinstance(value, str):
        return set(value.split())
    return {str(item) for item in value}
