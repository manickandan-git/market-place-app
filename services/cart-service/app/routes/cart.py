from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.dependencies.auth import (
    Principal,
    get_current_principal,
    get_optional_principal,
    require_scope,
)
from app.dependencies.headers import (
    optional_guest_token,
    optional_idempotency_key,
    required_version,
)
from app.routes.dependencies import get_cart_service
from app.schemas.cart import (
    CartItemCreate,
    CartItemUpdate,
    CartResponse,
    CheckoutReadinessResponse,
    ExpiredCartsResponse,
    GuestCartResponse,
    MarkCheckedOutRequest,
    MergeCartRequest,
)
from app.services import CartService

router = APIRouter()
OptionalPrincipal = Annotated[Principal | None, Depends(get_optional_principal)]
GuestToken = Annotated[str | None, Depends(optional_guest_token)]
IdempotencyKey = Annotated[str | None, Depends(optional_idempotency_key)]
Version = Annotated[int, Depends(required_version)]
Service = Annotated[CartService, Depends(get_cart_service)]
CheckoutPrincipal = Annotated[Principal, Depends(require_scope("cart:checkout"))]
ExpiryPrincipal = Annotated[Principal, Depends(require_scope("cart:expire"))]


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post(
    "/guest-carts",
    response_model=GuestCartResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["guest cart"],
)
async def create_guest_cart(request: Request, service: Service):
    token, cart = await service.create_guest_cart(request_id(request))
    return GuestCartResponse(cart_token=token, cart=CartResponse.from_cart(cart))


@router.get("/cart", response_model=CartResponse, tags=["cart"])
async def get_cart(
    principal: OptionalPrincipal,
    guest_token: GuestToken,
    service: Service,
):
    cart = await service.resolve_cart(principal, guest_token)
    return CartResponse.from_cart(cart)


@router.post(
    "/cart/items",
    response_model=CartResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["cart items"],
)
async def add_item(
    data: CartItemCreate,
    request: Request,
    principal: OptionalPrincipal,
    guest_token: GuestToken,
    service: Service,
    expected_version: Version,
    idempotency_key: IdempotencyKey,
):
    cart = await service.add_item(
        data,
        principal,
        guest_token,
        expected_version,
        idempotency_key,
        request_id(request),
    )
    return CartResponse.from_cart(cart)


@router.patch("/cart/items/{item_id}", response_model=CartResponse, tags=["cart items"])
async def update_item(
    item_id: UUID,
    data: CartItemUpdate,
    request: Request,
    principal: OptionalPrincipal,
    guest_token: GuestToken,
    service: Service,
    expected_version: Version,
):
    cart = await service.update_quantity(
        item_id,
        data.quantity,
        principal,
        guest_token,
        expected_version,
        request_id(request),
    )
    return CartResponse.from_cart(cart)


@router.delete(
    "/cart/items/{item_id}", response_model=CartResponse, tags=["cart items"]
)
async def remove_item(
    item_id: UUID,
    request: Request,
    principal: OptionalPrincipal,
    guest_token: GuestToken,
    service: Service,
    expected_version: Version,
):
    cart = await service.remove_item(
        item_id, principal, guest_token, expected_version, request_id(request)
    )
    return CartResponse.from_cart(cart)


@router.post(
    "/cart/items/{item_id}/save-for-later",
    response_model=CartResponse,
    tags=["saved items"],
)
async def save_for_later(
    item_id: UUID,
    request: Request,
    principal: OptionalPrincipal,
    guest_token: GuestToken,
    service: Service,
    expected_version: Version,
):
    cart = await service.save_for_later(
        item_id, principal, guest_token, expected_version, request_id(request)
    )
    return CartResponse.from_cart(cart)


@router.post(
    "/cart/saved-items/{item_id}/move-to-cart",
    response_model=CartResponse,
    tags=["saved items"],
)
async def move_saved_to_cart(
    item_id: UUID,
    request: Request,
    principal: OptionalPrincipal,
    guest_token: GuestToken,
    service: Service,
    expected_version: Version,
):
    cart = await service.move_saved_to_cart(
        item_id, principal, guest_token, expected_version, request_id(request)
    )
    return CartResponse.from_cart(cart)


@router.delete(
    "/cart/saved-items/{item_id}",
    response_model=CartResponse,
    tags=["saved items"],
)
async def delete_saved_item(
    item_id: UUID,
    request: Request,
    principal: OptionalPrincipal,
    guest_token: GuestToken,
    service: Service,
    expected_version: Version,
):
    cart = await service.delete_saved(
        item_id, principal, guest_token, expected_version, request_id(request)
    )
    return CartResponse.from_cart(cart)


@router.post(
    "/cart/readiness",
    response_model=CheckoutReadinessResponse,
    tags=["checkout"],
)
async def check_readiness(
    request: Request,
    principal: OptionalPrincipal,
    guest_token: GuestToken,
    service: Service,
    expected_version: Version,
):
    return await service.readiness(
        principal, guest_token, expected_version, request_id(request)
    )


@router.post("/cart/merge", response_model=CartResponse, tags=["cart"])
async def merge_guest_cart(
    data: MergeCartRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_current_principal)],
    service: Service,
):
    cart = await service.merge_guest(
        principal, data.guest_cart_token, request_id(request)
    )
    return CartResponse.from_cart(cart)


@router.delete("/cart", response_model=CartResponse, tags=["cart"])
async def clear_cart(
    request: Request,
    principal: OptionalPrincipal,
    guest_token: GuestToken,
    service: Service,
    expected_version: Version,
):
    cart = await service.clear(
        principal, guest_token, expected_version, request_id(request)
    )
    return CartResponse.from_cart(cart)


@router.post(
    "/internal/carts/{cart_id}/checked-out",
    response_model=CartResponse,
    tags=["integration"],
)
async def mark_checked_out(
    cart_id: UUID,
    data: MarkCheckedOutRequest,
    request: Request,
    principal: CheckoutPrincipal,
    service: Service,
):
    # principal (the cart:checkout-scoped service token) only proves the
    # caller is a trusted service, not which customer's cart to retire —
    # that comes from the request body. CartService.mark_checked_out still
    # verifies data.customer_id against the cart's own customer_id column
    # before doing anything, so a caller can't retire a cart it doesn't
    # name correctly.
    cart = await service.mark_checked_out(
        cart_id, data.customer_id, data.order_id, request_id(request)
    )
    return CartResponse.from_cart(cart)


@router.post(
    "/internal/carts/expire",
    response_model=ExpiredCartsResponse,
    tags=["integration"],
)
async def expire_carts(
    _principal: ExpiryPrincipal,
    service: Service,
):
    return ExpiredCartsResponse(expired_count=await service.repo.expire_due())
