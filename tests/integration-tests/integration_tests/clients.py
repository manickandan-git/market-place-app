from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import httpx


class ApiError(AssertionError):
    """Readable failure containing the upstream response body."""


class ServiceClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 20,
        verify: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            verify=verify,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        headers: Mapping[str, str] | None = None,
        expected: int | set[int] | tuple[int, ...] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        request_headers = {
            "X-Correlation-ID": f"it-{uuid4()}",
            **dict(headers or {}),
        }
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        response = await self._client.request(
            method,
            path,
            headers=request_headers,
            **kwargs,
        )
        if expected is not None:
            expected_codes = {expected} if isinstance(expected, int) else set(expected)
            if response.status_code not in expected_codes:
                raise ApiError(
                    f"{method} {response.request.url} returned "
                    f"{response.status_code}; expected {sorted(expected_codes)}. "
                    f"Body: {response.text[:2000]}"
                )
        return response

    async def json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.request(method, path, **kwargs)
        if not response.content:
            return None
        return response.json()


class MarketplaceClients:
    def __init__(self, settings: Any) -> None:
        options = {
            "timeout": settings.http_timeout_seconds,
            "verify": settings.verify_tls,
        }
        self.auth = ServiceClient(settings.auth_service_url, **options)
        self.user = ServiceClient(settings.user_service_url, **options)
        self.product = ServiceClient(settings.product_service_url, **options)
        self.inventory = ServiceClient(settings.inventory_service_url, **options)
        self.notification = ServiceClient(
            settings.notification_service_url,
            **options,
        )
        self.cart = ServiceClient(settings.cart_service_url, **options)
        self.order = ServiceClient(settings.order_service_url, **options)
        self.payment = ServiceClient(settings.payment_service_url, **options)
        self.shipping = ServiceClient(settings.shipping_service_url, **options)

    async def close(self) -> None:
        await self.auth.close()
        await self.user.close()
        await self.product.close()
        await self.inventory.close()
        await self.notification.close()
        await self.cart.close()
        await self.order.close()
        await self.payment.close()
        await self.shipping.close()

