from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.models.cart import CartStatus
from app.schemas.common import APIModel


class CartItemCreate(APIModel):
    product_id: UUID
    variant_id: UUID
    quantity: int = Field(ge=1, le=1000)


class CartItemUpdate(APIModel):
    quantity: int = Field(ge=1, le=1000)


class ProductSnapshot(APIModel):
    product_id: UUID
    variant_id: UUID
    sku: str
    product_name: str
    variant_name: str
    image_url: str | None = None
    unit_price: Decimal
    currency_code: str
    product_version: int


class CartItemResponse(APIModel):
    id: UUID
    product_id: UUID
    variant_id: UUID
    sku: str
    product_name: str
    variant_name: str
    image_url: str | None
    quantity: int
    unit_price: Decimal
    currency_code: str
    line_total: Decimal
    product_version: int
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_item(cls, item) -> Self:
        return cls(
            id=item.id,
            product_id=item.product_id,
            variant_id=item.variant_id,
            sku=item.sku,
            product_name=item.product_name,
            variant_name=item.variant_name,
            image_url=item.image_url,
            quantity=item.quantity,
            unit_price=item.unit_price,
            currency_code=item.currency_code,
            line_total=item.unit_price * item.quantity,
            product_version=item.product_version,
            version=item.version,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class SavedItemResponse(APIModel):
    id: UUID
    product_id: UUID
    variant_id: UUID
    sku: str
    product_name: str
    variant_name: str
    image_url: str | None
    unit_price: Decimal
    currency_code: str
    created_at: datetime


class CartResponse(APIModel):
    id: UUID
    customer_id: UUID | None
    status: CartStatus
    currency_code: str
    items: list[CartItemResponse]
    saved_items: list[SavedItemResponse]
    total_quantity: int
    subtotal: Decimal
    expires_at: datetime
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_cart(cls, cart) -> Self:
        items = [CartItemResponse.from_item(item) for item in cart.items]
        return cls(
            id=cart.id,
            customer_id=cart.customer_id,
            status=cart.status,
            currency_code=cart.currency_code,
            items=items,
            saved_items=[
                SavedItemResponse.model_validate(item) for item in cart.saved_items
            ],
            total_quantity=sum(item.quantity for item in items),
            subtotal=sum((item.line_total for item in items), start=Decimal("0.00")),
            expires_at=cart.expires_at,
            version=cart.version,
            created_at=cart.created_at,
            updated_at=cart.updated_at,
        )


class GuestCartResponse(APIModel):
    cart_token: str
    cart: CartResponse


class MergeCartRequest(APIModel):
    guest_cart_token: str = Field(min_length=32, max_length=200)


class AvailabilityLine(APIModel):
    item_id: UUID
    sku: str
    requested_quantity: int
    available_quantity: int
    is_available: bool


class CheckoutReadinessResponse(APIModel):
    cart_id: UUID
    ready: bool
    price_changed: bool
    unavailable_items: list[AvailabilityLine]
    items: list[AvailabilityLine]
    subtotal: Decimal
    currency_code: str


class MarkCheckedOutRequest(APIModel):
    order_id: UUID


class CartEvent(APIModel):
    cart_id: UUID
    customer_id: UUID | None
    event_type: str


class ExpiredCartsResponse(APIModel):
    expired_count: int


class CartPatch(APIModel):
    currency_code: str | None = Field(
        default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$"
    )

    @model_validator(mode="after")
    def non_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one cart field must be provided")
        return self
