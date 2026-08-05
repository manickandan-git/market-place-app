from __future__ import annotations

from datetime import datetime
from uuid import UUID

import httpx

from app.config import Settings
from app.exceptions import ServiceError


def _headers(token: str, request_id: str | None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if request_id:
        headers["X-Request-ID"] = request_id
    return headers


class OrderClient:
    """Calls Order's existing internal fulfillment callback — the only
    endpoint Shipping calls on Order. See
    services/order-service/docs/shipping-service-scope.md."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    async def advance_fulfillment(
        self,
        order_id: UUID,
        status: str,
        shipment_reference: str | None,
        occurred_at: datetime | None,
        service_token: str,
        request_id: str | None,
    ) -> None:
        owns = self.client is None
        client = self.client or httpx.AsyncClient(
            base_url=self.settings.order_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        body = {"status": status}
        if shipment_reference is not None:
            body["shipment_reference"] = shipment_reference
        if occurred_at is not None:
            body["occurred_at"] = occurred_at.isoformat()
        try:
            response = await client.post(
                f"/api/v1/internal/orders/{order_id}/fulfillment",
                json=body,
                headers=_headers(service_token, request_id),
            )
        except httpx.RequestError as exc:
            raise ServiceError(
                503, "order_unavailable", "Order Service is unavailable"
            ) from exc
        finally:
            if owns:
                await client.aclose()
        if response.status_code == 404:
            raise ServiceError(404, "order_not_found", "Order was not found")
        if response.status_code == 409:
            raise ServiceError(
                409,
                "invalid_order_transition",
                "Order is not in a state that allows this fulfillment update",
            )
        if response.status_code >= 400:
            raise ServiceError(
                502, "order_callback_failed", "Order Service callback failed"
            )
