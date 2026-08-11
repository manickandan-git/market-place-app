import hashlib
import logging
import time

import httpx

from app.config import Settings
from app.event_logger import log_event
from app.exceptions import ServiceError

logger = logging.getLogger(__name__)


class ProductClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client

    async def search_products(
        self, query: str | None, category_id: str | None, request_id: str | None
    ) -> list[dict]:
        headers = {"X-Request-ID": request_id} if request_id else {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.product_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        params = {"page_size": 10}
        if query:
            params["q"] = query
        if category_id:
            params["category_id"] = category_id
        start = time.monotonic()
        try:
            response = await client.get(
                "/api/v1/products", params=params, headers=headers
            )
        except httpx.RequestError as exc:
            _log_downstream(
                "product-service", "search_products", None, start, request_id
            )
            raise ServiceError(
                503, "product_service_unavailable", "Product Service is unavailable"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        _log_downstream(
            "product-service",
            "search_products",
            response.status_code,
            start,
            request_id,
        )
        if response.status_code >= 400:
            raise ServiceError(502, "product_service_error", "Product search failed")
        return response.json()["items"]

    async def get_product_by_slug(
        self, slug: str, request_id: str | None
    ) -> dict | None:
        headers = {"X-Request-ID": request_id} if request_id else {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.product_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        start = time.monotonic()
        try:
            response = await client.get(
                f"/api/v1/products/by-slug/{slug}", headers=headers
            )
        except httpx.RequestError as exc:
            _log_downstream(
                "product-service", "get_product_by_slug", None, start, request_id
            )
            raise ServiceError(
                503, "product_service_unavailable", "Product Service is unavailable"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        _log_downstream(
            "product-service",
            "get_product_by_slug",
            response.status_code,
            start,
            request_id,
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ServiceError(502, "product_service_error", "Product lookup failed")
        return response.json()

    async def list_categories(self, request_id: str | None) -> list[dict]:
        headers = {"X-Request-ID": request_id} if request_id else {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.product_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        start = time.monotonic()
        try:
            response = await client.get("/api/v1/categories", headers=headers)
        except httpx.RequestError as exc:
            _log_downstream(
                "product-service", "list_categories", None, start, request_id
            )
            raise ServiceError(
                503, "product_service_unavailable", "Product Service is unavailable"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        _log_downstream(
            "product-service",
            "list_categories",
            response.status_code,
            start,
            request_id,
        )
        if response.status_code >= 400:
            raise ServiceError(502, "product_service_error", "Category list failed")
        return response.json()


class InventoryClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client

    async def get_availability(self, sku: str, request_id: str | None) -> dict:
        headers = {"X-Request-ID": request_id} if request_id else {}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.inventory_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        start = time.monotonic()
        try:
            response = await client.get(f"/api/v1/availability/{sku}", headers=headers)
        except httpx.RequestError as exc:
            _log_downstream(
                "inventory-service", "get_availability", None, start, request_id
            )
            raise ServiceError(
                503,
                "inventory_service_unavailable",
                "Inventory Service is unavailable",
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        _log_downstream(
            "inventory-service",
            "get_availability",
            response.status_code,
            start,
            request_id,
        )
        if response.status_code >= 400:
            raise ServiceError(
                502, "inventory_service_error", "Availability lookup failed"
            )
        return response.json()


class OrderClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client

    async def get_my_orders(self, access_token: str, request_id: str | None) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        if request_id:
            headers["X-Request-ID"] = request_id
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.order_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        start = time.monotonic()
        try:
            response = await client.get("/api/v1/orders", headers=headers)
        except httpx.RequestError as exc:
            _log_downstream("order-service", "get_my_orders", None, start, request_id)
            raise ServiceError(
                503, "order_service_unavailable", "Order Service is unavailable"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        _log_downstream(
            "order-service", "get_my_orders", response.status_code, start, request_id
        )
        if response.status_code == 401:
            raise ServiceError(
                401,
                "order_service_unauthorized",
                "Access token was rejected by Order Service",
            )
        if response.status_code >= 400:
            raise ServiceError(502, "order_service_error", "Order lookup failed")
        return response.json()

    async def get_order(
        self, order_id: str, access_token: str, request_id: str | None
    ) -> dict | None:
        headers = {"Authorization": f"Bearer {access_token}"}
        if request_id:
            headers["X-Request-ID"] = request_id
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.order_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        start = time.monotonic()
        try:
            response = await client.get(f"/api/v1/orders/{order_id}", headers=headers)
        except httpx.RequestError as exc:
            _log_downstream("order-service", "get_order", None, start, request_id)
            raise ServiceError(
                503, "order_service_unavailable", "Order Service is unavailable"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        _log_downstream(
            "order-service", "get_order", response.status_code, start, request_id
        )
        if response.status_code == 401:
            raise ServiceError(
                401,
                "order_service_unauthorized",
                "Access token was rejected by Order Service",
            )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ServiceError(502, "order_service_error", "Order lookup failed")
        return response.json()


class CartClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client

    def _add_item_idempotency_key(
        self, product_id: str, variant_id: str, quantity: int
    ) -> str:
        # Content-derived, not random: two add_to_cart calls for the same
        # product/variant/quantity within the same time bucket collide onto
        # the same key, so cart-service's existing idempotency dedup
        # (services/cart-service/app/services/cart_service.py's add_item)
        # returns the cached cart instead of double-adding. This is what
        # closes docs/guardrails.md finding B: chat.py's wall-clock timeout
        # can cancel this call after the POST already reached cart-service,
        # and if the buyer/model retries shortly after (the realistic case
        # — there's no automatic HTTP-level retry anywhere in this stack),
        # this makes that retry a safe no-op instead of a second add.
        # cart-service scopes idempotency keys per-actor server-side, so
        # nothing about the caller's identity needs to be in the key here.
        window = self.settings.cart_add_idempotency_window_seconds
        bucket = int(time.time() // window)
        raw = f"{product_id}:{variant_id}:{quantity}:{bucket}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def add_item(
        self,
        access_token: str,
        product_id: str,
        variant_id: str,
        quantity: int,
        request_id: str | None,
    ) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        if request_id:
            headers["X-Request-ID"] = request_id
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.cart_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        start = time.monotonic()
        try:
            cart_response = await client.get("/api/v1/cart", headers=headers)
            if cart_response.status_code == 401:
                raise ServiceError(
                    401,
                    "cart_service_unauthorized",
                    "Access token was rejected by Cart Service",
                )
            if cart_response.status_code >= 400:
                raise ServiceError(502, "cart_service_error", "Cart lookup failed")
            version = cart_response.json()["version"]
            add_headers = {
                **headers,
                "If-Match-Version": str(version),
                "Idempotency-Key": self._add_item_idempotency_key(
                    product_id, variant_id, quantity
                ),
            }
            response = await client.post(
                "/api/v1/cart/items",
                headers=add_headers,
                json={
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "quantity": quantity,
                },
            )
        except httpx.RequestError as exc:
            _log_downstream("cart-service", "add_item", None, start, request_id)
            raise ServiceError(
                503, "cart_service_unavailable", "Cart Service is unavailable"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        _log_downstream(
            "cart-service", "add_item", response.status_code, start, request_id
        )
        if response.status_code == 401:
            raise ServiceError(
                401,
                "cart_service_unauthorized",
                "Access token was rejected by Cart Service",
            )
        if response.status_code >= 400:
            raise ServiceError(502, "cart_service_error", "Add to cart failed")
        return response.json()

    async def remove_item(
        self,
        access_token: str,
        product_id: str,
        variant_id: str,
        request_id: str | None,
    ) -> dict | None:
        headers = {"Authorization": f"Bearer {access_token}"}
        if request_id:
            headers["X-Request-ID"] = request_id
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            base_url=self.settings.cart_service_url,
            timeout=self.settings.downstream_timeout_seconds,
        )
        start = time.monotonic()
        try:
            cart_response = await client.get("/api/v1/cart", headers=headers)
            if cart_response.status_code == 401:
                raise ServiceError(
                    401,
                    "cart_service_unauthorized",
                    "Access token was rejected by Cart Service",
                )
            if cart_response.status_code >= 400:
                raise ServiceError(502, "cart_service_error", "Cart lookup failed")
            cart = cart_response.json()
            item = next(
                (
                    i
                    for i in cart["items"]
                    if i["product_id"] == product_id and i["variant_id"] == variant_id
                ),
                None,
            )
            if item is None:
                return None
            remove_headers = {**headers, "If-Match-Version": str(cart["version"])}
            response = await client.delete(
                f"/api/v1/cart/items/{item['id']}", headers=remove_headers
            )
        except httpx.RequestError as exc:
            _log_downstream("cart-service", "remove_item", None, start, request_id)
            raise ServiceError(
                503, "cart_service_unavailable", "Cart Service is unavailable"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()
        _log_downstream(
            "cart-service", "remove_item", response.status_code, start, request_id
        )
        if response.status_code == 401:
            raise ServiceError(
                401,
                "cart_service_unauthorized",
                "Access token was rejected by Cart Service",
            )
        if response.status_code >= 400:
            raise ServiceError(502, "cart_service_error", "Remove from cart failed")
        return response.json()


def _log_downstream(
    service: str,
    operation: str,
    status_code: int | None,
    start: float,
    request_id: str | None,
) -> None:
    log_event(
        logger,
        "downstream_call",
        service=service,
        operation=operation,
        status_code=status_code,
        duration_ms=round((time.monotonic() - start) * 1000),
        request_id=request_id,
    )
