from uuid import UUID

import httpx

from app.config import Settings
from app.exceptions import ServiceError
from app.schemas.cart import ProductSnapshot


class ProductClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client

    async def get_snapshot(
        self, product_id: UUID, variant_id: UUID, request_id: str | None
    ) -> ProductSnapshot:
        headers = {"X-Request-ID": request_id} if request_id else {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.product_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        try:
            response = await client.get(
                f"/api/v1/products/{product_id}", headers=headers
            )
        except httpx.RequestError as exc:
            raise ServiceError(
                503, "product_service_unavailable", "Product Service is unavailable"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code == 404:
            raise ServiceError(422, "product_not_available", "Product is not active")
        if response.status_code >= 400:
            raise ServiceError(502, "product_service_error", "Product lookup failed")
        product = response.json()
        variant = next(
            (
                v
                for v in product.get("variants", [])
                if str(v.get("id")) == str(variant_id)
            ),
            None,
        )
        if not variant or not variant.get("is_active", False):
            raise ServiceError(422, "variant_not_available", "Variant is not active")
        images = sorted(
            product.get("images", []), key=lambda value: value["sort_order"]
        )
        return ProductSnapshot(
            product_id=product_id,
            variant_id=variant_id,
            sku=variant["sku"],
            product_name=product["name"],
            variant_name=variant["name"],
            image_url=images[0]["url"] if images else None,
            unit_price=variant["price_amount"],
            currency_code=variant["currency_code"],
            product_version=variant["version"],
        )


class InventoryClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client

    async def availability(
        self, sku: str, quantity: int, request_id: str | None
    ) -> tuple[int, bool]:
        headers = {"X-Request-ID": request_id} if request_id else {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.inventory_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        try:
            response = await client.get(
                f"/api/v1/availability/{sku}",
                params={"quantity": quantity},
                headers=headers,
            )
        except httpx.RequestError as exc:
            raise ServiceError(
                503,
                "inventory_service_unavailable",
                "Inventory Service is unavailable",
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code >= 400:
            raise ServiceError(
                502, "inventory_service_error", "Availability lookup failed"
            )
        data = response.json()
        return int(data["available_quantity"]), bool(data["is_available"])
