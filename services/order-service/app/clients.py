from __future__ import annotations

from datetime import datetime
from uuid import UUID

import httpx

from app.config import Settings
from app.exceptions import ServiceError
from app.schemas import (
    BatchReservationRequest,
    BatchReservationResponse,
    CartSnapshot,
)


def _headers(token: str | None, request_id: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if request_id:
        headers["X-Request-ID"] = request_id
    return headers


class CartClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    async def snapshot(
        self, cart_id: UUID, version: int, token: str, request_id: str | None
    ) -> CartSnapshot:
        owns = self.client is None
        client = self.client or httpx.AsyncClient(
            base_url=self.settings.cart_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        try:
            cart_response = await client.get(
                "/api/v1/cart", headers=_headers(token, request_id)
            )
            ready_response = await client.post(
                "/api/v1/cart/readiness",
                headers={
                    **_headers(token, request_id),
                    "If-Match-Version": str(version),
                },
            )
        except httpx.RequestError as exc:
            raise ServiceError(
                503, "cart_unavailable", "Cart Service is unavailable"
            ) from exc
        finally:
            if owns:
                await client.aclose()
        if cart_response.status_code >= 400:
            raise ServiceError(422, "cart_not_available", "Cart could not be loaded")
        cart = cart_response.json()
        if str(cart.get("id")) != str(cart_id):
            raise ServiceError(
                409, "cart_mismatch", "Requested cart is not the active cart"
            )
        if cart.get("version") != version:
            raise ServiceError(409, "cart_version_conflict", "Cart has changed")
        if ready_response.status_code >= 400:
            raise ServiceError(422, "cart_not_ready", "Cart readiness check failed")
        readiness = ready_response.json()
        if not readiness.get("ready") or readiness.get("price_changed"):
            raise ServiceError(
                409, "cart_not_ready", "Cart price or availability changed"
            )
        return CartSnapshot.model_validate(cart)

    async def mark_checked_out(
        self, cart_id: UUID, order_id: UUID, token: str, request_id: str | None
    ) -> None:
        owns = self.client is None
        client = self.client or httpx.AsyncClient(
            base_url=self.settings.cart_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        try:
            response = await client.post(
                f"/api/v1/internal/carts/{cart_id}/checked-out",
                json={"order_id": str(order_id)},
                headers=_headers(token, request_id),
            )
        except httpx.RequestError as exc:
            raise ServiceError(503, "cart_unavailable", "Cart update failed") from exc
        finally:
            if owns:
                await client.aclose()
        if response.status_code >= 400:
            raise ServiceError(
                502, "cart_update_failed", "Cart checkout handoff failed"
            )


class ProductClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    async def seller_for_product(
        self, product_id: UUID, request_id: str | None
    ) -> UUID:
        owns = self.client is None
        client = self.client or httpx.AsyncClient(
            base_url=self.settings.product_service_url
            if hasattr(self.settings, "product_service_url")
            else "http://localhost:8004",
            timeout=self.settings.downstream_timeout_seconds,
        )
        try:
            response = await client.get(
                f"/api/v1/products/{product_id}", headers=_headers(None, request_id)
            )
        except httpx.RequestError as exc:
            raise ServiceError(
                503, "product_unavailable", "Product Service is unavailable"
            ) from exc
        finally:
            if owns:
                await client.aclose()
        if response.status_code >= 400:
            raise ServiceError(422, "product_not_available", "Product is not available")
        return UUID(str(response.json()["owner_user_id"]))


class InventoryClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client

    async def reserve_batch(
        self,
        data: BatchReservationRequest,
        token: str,
        idempotency_key: str,
        request_id: str | None,
    ) -> BatchReservationResponse:
        response = await self._post(
            "/api/v1/internal/checkout/reservations/batch",
            data.model_dump(mode="json"),
            token,
            request_id,
            idempotency_key,
        )
        if response.status_code in {409, 422}:
            raise ServiceError(
                409, "inventory_unavailable", "Stock could not be reserved"
            )
        if response.status_code >= 400:
            raise ServiceError(502, "inventory_error", "Inventory reservation failed")
        return BatchReservationResponse.model_validate(response.json())

    async def commit_group(
        self, group_id: UUID, order_reference: str, token: str, request_id: str | None
    ) -> None:
        response = await self._post(
            f"/api/v1/internal/checkout/reservations/{group_id}/commit",
            {"order_reference": order_reference},
            token,
            request_id,
            order_reference,
        )
        if response.status_code >= 400:
            raise ServiceError(
                502, "inventory_commit_failed", "Inventory commit failed"
            )

    async def release_group(
        self, group_id: UUID, reason: str, token: str, request_id: str | None
    ) -> None:
        response = await self._post(
            f"/api/v1/internal/checkout/reservations/{group_id}/release",
            {"reason": "customer_cancelled", "note": reason},
            token,
            request_id,
            f"release:{group_id}",
        )
        if response.status_code >= 400 and response.status_code != 409:
            raise ServiceError(
                502, "inventory_release_failed", "Inventory release failed"
            )

    async def _post(
        self,
        path: str,
        json: dict,
        token: str,
        request_id: str | None,
        idempotency_key: str,
    ) -> httpx.Response:
        owns = self.client is None
        client = self.client or httpx.AsyncClient(
            base_url=self.settings.inventory_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        try:
            return await client.post(
                path,
                json=json,
                headers={
                    **_headers(token, request_id),
                    "Idempotency-Key": idempotency_key,
                },
            )
        except httpx.RequestError as exc:
            raise ServiceError(
                503, "inventory_unavailable", "Inventory Service is unavailable"
            ) from exc
        finally:
            if owns:
                await client.aclose()


class NotificationClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def order_event(
        self, customer_id: UUID, order_number: str, event: str, request_id: str | None
    ) -> None:
        payload = {
            "template": event,
            "recipient_user_id": str(customer_id),
            "data": {"order_number": order_number},
            "occurred_at": datetime.utcnow().isoformat(),
        }
        headers = {"X-Internal-API-Key": self.settings.notification_internal_api_key}
        if request_id:
            headers["X-Request-ID"] = request_id
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.notification_service_url,
                timeout=self.settings.downstream_timeout_seconds,
            ) as client:
                await client.post(
                    "/api/v1/internal/notifications", json=payload, headers=headers
                )
        except httpx.RequestError:
            # The durable outbox remains authoritative; delivery is retryable.
            return
