from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models import OrderStatus, PaymentStatus


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AddressSnapshot(APIModel):
    full_name: str = Field(min_length=1, max_length=160)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state_or_region: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=30)
    country_code: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    phone: str | None = Field(default=None, max_length=40)


class OrderCreate(APIModel):
    cart_id: UUID
    cart_version: int = Field(ge=1)
    shipping_address: AddressSnapshot
    billing_address: AddressSnapshot | None = None


class OrderItemResponse(APIModel):
    id: UUID
    product_id: UUID
    variant_id: UUID
    seller_id: UUID
    sku: str
    product_name: str
    variant_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    product_version: int


class OrderResponse(APIModel):
    id: UUID
    order_number: str
    customer_id: UUID
    cart_id: UUID
    status: OrderStatus
    payment_status: PaymentStatus
    currency_code: str
    subtotal: Decimal
    tax_total: Decimal
    shipping_total: Decimal
    discount_total: Decimal
    grand_total: Decimal
    shipping_address: dict
    billing_address: dict
    reservation_group_id: UUID | None
    payment_reference: str | None
    cancellation_reason: str | None
    version: int
    items: list[OrderItemResponse]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_order(cls, order) -> Self:
        return cls.model_validate(order)


class Page(APIModel):
    items: list[OrderResponse]
    page: int
    page_size: int
    total_items: int


class CancelOrder(APIModel):
    reason: str = Field(min_length=3, max_length=1000)


class PaymentAuthorized(APIModel):
    payment_reference: str = Field(min_length=1, max_length=160)
    authorized_amount: Decimal = Field(gt=0)
    currency_code: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")


class PaymentFailed(APIModel):
    payment_reference: str | None = Field(default=None, max_length=160)
    reason: str = Field(min_length=1, max_length=1000)


class PaymentRefunded(APIModel):
    """refunded_amount is the *cumulative* amount refunded on the payment so
    far (not just this refund), so order-service can deterministically
    derive REFUNDED vs PARTIALLY_REFUNDED without trusting a status enum
    from the caller. No payment_reference field: refunding must not
    overwrite Order.payment_reference, which still identifies the original
    charge."""

    refunded_amount: Decimal = Field(gt=0)
    currency_code: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    reason: str | None = Field(default=None, max_length=120)


class FulfillmentUpdate(APIModel):
    status: OrderStatus
    shipment_reference: str | None = Field(default=None, max_length=160)
    occurred_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def fulfillment_status_only(self) -> Self:
        allowed = {
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        }
        if self.status not in allowed:
            raise ValueError("Fulfillment may set processing, shipped, or delivered")
        return self


class CartItemSnapshot(APIModel):
    product_id: UUID
    variant_id: UUID
    seller_id: UUID | None = None
    sku: str
    product_name: str
    variant_name: str
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    currency_code: str
    product_version: int


class CartSnapshot(APIModel):
    id: UUID
    customer_id: UUID
    status: str
    currency_code: str
    subtotal: Decimal
    version: int
    items: list[CartItemSnapshot]


class BatchReservationLine(APIModel):
    sku: str
    quantity: int
    seller_id: UUID


class BatchReservationRequest(APIModel):
    cart_reference: str
    order_reference: str
    expires_at: AwareDatetime
    lines: list[BatchReservationLine]


class BatchReservationResponse(APIModel):
    reservation_group_id: UUID
    reservation_ids: list[UUID]
    expires_at: datetime
