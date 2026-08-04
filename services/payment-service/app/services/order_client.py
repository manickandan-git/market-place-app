from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

import httpx

from app.config import Settings
from app.exceptions import ServiceError


@dataclass(frozen=True)
class OrderSnapshot:
    order_id: UUID
    status: str
    grand_total: Decimal
    currency_code: str


def _headers(token: str, request_id: str | None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if request_id:
        headers["X-Request-ID"] = request_id
    return headers


class OrderClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    async def get_order(
        self,
        order_id: UUID,
        buyer_token: str,
        request_id: str | None,
    ) -> OrderSnapshot:
        """Order-service enforces ownership itself (404s a non-owned order),
        so no separate check is needed here — the buyer's own token is what
        is forwarded."""
        response = await self._request(
            "GET",
            f"/api/v1/orders/{order_id}",
            buyer_token,
            request_id,
        )
        if response.status_code == 404:
            raise ServiceError(404, "order_not_found", "Order was not found")
        if response.status_code >= 400:
            raise ServiceError(502, "order_error", "Could not load order")
        data = response.json()
        return OrderSnapshot(
            order_id=order_id,
            status=data["status"],
            grand_total=Decimal(str(data["grand_total"])),
            currency_code=data["currency_code"],
        )

    async def payment_authorized(
        self,
        order_id: UUID,
        payment_reference: str,
        amount: Decimal,
        currency_code: str,
        service_token: str,
        request_id: str | None,
    ) -> None:
        response = await self._request(
            "POST",
            f"/api/v1/internal/orders/{order_id}/payment-authorized",
            service_token,
            request_id,
            json={
                "payment_reference": payment_reference,
                "authorized_amount": str(amount),
                "currency_code": currency_code,
            },
        )
        if response.status_code >= 400:
            raise ServiceError(
                502, "order_callback_failed", "Order Service callback failed"
            )

    async def payment_failed(
        self,
        order_id: UUID,
        payment_reference: str | None,
        reason: str,
        service_token: str,
        request_id: str | None,
    ) -> None:
        response = await self._request(
            "POST",
            f"/api/v1/internal/orders/{order_id}/payment-failed",
            service_token,
            request_id,
            json={"payment_reference": payment_reference, "reason": reason},
        )
        if response.status_code >= 400:
            raise ServiceError(
                502, "order_callback_failed", "Order Service callback failed"
            )

    async def payment_refunded(
        self,
        order_id: UUID,
        refunded_amount: Decimal,
        currency_code: str,
        reason: str | None,
        service_token: str,
        request_id: str | None,
    ) -> None:
        """refunded_amount must be the cumulative total refunded on the
        payment so far, not just the latest refund — order-service derives
        refunded/partially_refunded from that against its own grand_total."""
        response = await self._request(
            "POST",
            f"/api/v1/internal/orders/{order_id}/payment-refunded",
            service_token,
            request_id,
            json={
                "refunded_amount": str(refunded_amount),
                "currency_code": currency_code,
                "reason": reason,
            },
        )
        if response.status_code >= 400:
            raise ServiceError(
                502, "order_callback_failed", "Order Service callback failed"
            )

    async def _request(
        self,
        method: str,
        path: str,
        token: str,
        request_id: str | None,
        *,
        json: dict | None = None,
    ) -> httpx.Response:
        owns = self.client is None
        client = self.client or httpx.AsyncClient(
            base_url=self.settings.order_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        try:
            return await client.request(
                method, path, json=json, headers=_headers(token, request_id)
            )
        except httpx.RequestError as exc:
            raise ServiceError(
                503, "order_unavailable", "Order Service is unavailable"
            ) from exc
        finally:
            if owns:
                await client.aclose()
