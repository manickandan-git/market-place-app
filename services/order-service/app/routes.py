from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, bearer, current_principal, require_roles, require_scope
from app.auth_client import AuthClient
from app.clients import CartClient, InventoryClient, NotificationClient, ProductClient
from app.config import Settings, get_settings
from app.database import get_session
from app.exceptions import ServiceError
from app.schemas import (
    CancelOrder,
    FulfillmentUpdate,
    OrderCreate,
    OrderResponse,
    Page,
    PaymentAuthorized,
    PaymentFailed,
    PaymentRefunded,
)
from app.service import OrderService

router = APIRouter()
health_router = APIRouter()
Buyer = Annotated[Principal, Depends(require_roles("buyer", "admin"))]
PaymentService = Annotated[Principal, Depends(require_scope("orders:payment"))]
FulfillmentService = Annotated[Principal, Depends(require_scope("orders:fulfillment"))]


@lru_cache
def get_auth_client() -> AuthClient:
    # Must be a singleton: its whole purpose is caching the service token
    # across requests instead of re-authenticating on every callback.
    return AuthClient(get_settings())


async def order_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    auth_client: AuthClient = Depends(get_auth_client),
) -> OrderService:
    return OrderService(
        session,
        settings,
        CartClient(settings),
        ProductClient(settings),
        InventoryClient(settings),
        NotificationClient(settings),
        auth_client,
    )


Service = Annotated[OrderService, Depends(order_service)]


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None:
        raise ServiceError(401, "token_required", "Bearer token is required")
    return credentials.credentials


@health_router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "order-service"}


@health_router.get("/ready", tags=["health"])
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    from sqlalchemy import text

    await session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["orders"],
)
async def create_order(
    data: OrderCreate,
    request: Request,
    principal: Buyer,
    service: Service,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
) -> OrderResponse:
    order = await service.create(
        data,
        principal,
        token(credentials),
        idempotency_key,
        request_id(request),
    )
    return OrderResponse.from_order(order)


@router.get("/orders", response_model=Page, tags=["orders"])
async def list_orders(
    principal: Annotated[Principal, Depends(current_principal)],
    service: Service,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page:
    items, total = await service.repo.list_for_customer(
        principal.subject, page, page_size
    )
    return Page(
        items=[OrderResponse.from_order(item) for item in items],
        page=page,
        page_size=page_size,
        total_items=total,
    )


@router.get("/orders/{order_id}", response_model=OrderResponse, tags=["orders"])
async def get_order(
    order_id: UUID,
    principal: Annotated[Principal, Depends(current_principal)],
    service: Service,
) -> OrderResponse:
    return OrderResponse.from_order(await service.customer_order(order_id, principal))


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse, tags=["orders"])
async def cancel_order(
    order_id: UUID,
    data: CancelOrder,
    request: Request,
    principal: Buyer,
    service: Service,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    expected_version: Annotated[int, Header(alias="If-Match", ge=1)],
) -> OrderResponse:
    order = await service.cancel(
        order_id,
        data,
        principal,
        token(credentials),
        expected_version,
        request_id(request),
    )
    return OrderResponse.from_order(order)


@router.post(
    "/internal/orders/{order_id}/payment-authorized",
    response_model=OrderResponse,
    tags=["integration"],
)
async def payment_authorized(
    order_id: UUID,
    data: PaymentAuthorized,
    request: Request,
    principal: PaymentService,
    service: Service,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> OrderResponse:
    order = await service.payment_authorized(
        order_id, data, principal, token(credentials), request_id(request)
    )
    return OrderResponse.from_order(order)


@router.post(
    "/internal/orders/{order_id}/payment-failed",
    response_model=OrderResponse,
    tags=["integration"],
)
async def payment_failed(
    order_id: UUID,
    data: PaymentFailed,
    request: Request,
    principal: PaymentService,
    service: Service,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> OrderResponse:
    order = await service.payment_failed(
        order_id, data, principal, token(credentials), request_id(request)
    )
    return OrderResponse.from_order(order)


@router.post(
    "/internal/orders/{order_id}/payment-refunded",
    response_model=OrderResponse,
    tags=["integration"],
)
async def payment_refunded(
    order_id: UUID,
    data: PaymentRefunded,
    request: Request,
    principal: PaymentService,
    service: Service,
) -> OrderResponse:
    order = await service.payment_refunded(
        order_id, data, principal, request_id(request)
    )
    return OrderResponse.from_order(order)


@router.post(
    "/internal/orders/{order_id}/fulfillment",
    response_model=OrderResponse,
    tags=["integration"],
)
async def fulfillment_update(
    order_id: UUID,
    data: FulfillmentUpdate,
    request: Request,
    principal: FulfillmentService,
    service: Service,
) -> OrderResponse:
    order = await service.fulfillment(order_id, data, principal, request_id(request))
    return OrderResponse.from_order(order)
