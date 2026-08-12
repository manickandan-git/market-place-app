from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.models.inventory import (
    MovementReason,
    MovementType,
    ReservationStatus,
)
from app.schemas.common import APIModel

SKU_PATTERN = r"^[A-Za-z0-9._-]+$"
WAREHOUSE_CODE_PATTERN = r"^[A-Za-z0-9_-]+$"


def normalize_upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


class WarehouseCreate(APIModel):
    code: str = Field(min_length=2, max_length=40, pattern=WAREHOUSE_CODE_PATTERN)
    name: str = Field(min_length=2, max_length=160)
    address_reference: str | None = Field(default=None, max_length=200)
    is_active: bool = True

    _normalize_code = field_validator("code", mode="before")(normalize_upper)


class CatalogSkuSync(APIModel):
    """Product Service event projection payload."""

    product_id: UUID
    variant_id: UUID
    seller_id: UUID
    sku: str = Field(min_length=2, max_length=80, pattern=SKU_PATTERN)
    is_active: bool

    _normalize_sku = field_validator("sku", mode="before")(normalize_upper)


class CatalogSkuResponse(APIModel):
    variant_id: UUID
    product_id: UUID
    seller_id: UUID
    sku: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int


class WarehouseUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    address_reference: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None

    @model_validator(mode="after")
    def non_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one warehouse field must be provided")
        return self


class WarehouseResponse(APIModel):
    id: UUID
    code: str
    name: str
    address_reference: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int


class InventoryItemCreate(APIModel):
    warehouse_id: UUID
    product_id: UUID
    variant_id: UUID
    sku: str = Field(min_length=2, max_length=80, pattern=SKU_PATTERN)
    initial_quantity: int = Field(default=0, ge=0, le=1_000_000_000)
    low_stock_threshold: int = Field(default=5, ge=0, le=1_000_000)
    is_active: bool = True

    _normalize_sku = field_validator("sku", mode="before")(normalize_upper)


class InventoryItemUpdate(APIModel):
    low_stock_threshold: int | None = Field(default=None, ge=0, le=1_000_000)
    is_active: bool | None = None

    @model_validator(mode="after")
    def non_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one inventory field must be provided")
        return self


class StockAdjustment(APIModel):
    quantity_delta: int = Field(ge=-1_000_000_000, le=1_000_000_000)
    reason: MovementReason
    reference_type: str | None = Field(default=None, max_length=60)
    reference_id: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def non_zero(self) -> Self:
        if self.quantity_delta == 0:
            raise ValueError("quantity_delta must not be zero")
        return self


class InventoryItemResponse(APIModel):
    id: UUID
    warehouse_id: UUID
    product_id: UUID
    variant_id: UUID
    seller_id: UUID
    sku: str
    on_hand_quantity: int
    reserved_quantity: int
    available_quantity: int
    low_stock_threshold: int
    is_low_stock: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int

    @classmethod
    def from_item(cls, item) -> Self:
        return cls(
            id=item.id,
            warehouse_id=item.warehouse_id,
            product_id=item.product_id,
            variant_id=item.variant_id,
            seller_id=item.seller_id,
            sku=item.sku,
            on_hand_quantity=item.on_hand_quantity,
            reserved_quantity=item.reserved_quantity,
            available_quantity=item.available_quantity,
            low_stock_threshold=item.low_stock_threshold,
            is_low_stock=item.available_quantity <= item.low_stock_threshold,
            is_active=item.is_active,
            created_at=item.created_at,
            updated_at=item.updated_at,
            version=item.version,
        )


class AvailabilityResponse(APIModel):
    sku: str
    available_quantity: int
    is_available: bool


class ReservationCreate(APIModel):
    inventory_item_id: UUID
    quantity: int = Field(gt=0, le=1_000_000)
    cart_reference: str | None = Field(default=None, max_length=120)
    expires_at: AwareDatetime | None = None


class ReservationCommit(APIModel):
    order_reference: str = Field(min_length=1, max_length=120)


class ReservationRelease(APIModel):
    reason: MovementReason = MovementReason.CUSTOMER_CANCELLED
    note: str | None = Field(default=None, max_length=2000)


class ReservationResponse(APIModel):
    id: UUID
    inventory_item_id: UUID
    customer_id: UUID
    cart_reference: str | None
    order_reference: str | None
    quantity: int
    status: ReservationStatus
    expires_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class BatchReservationLine(APIModel):
    sku: str = Field(min_length=2, max_length=80, pattern=SKU_PATTERN)
    seller_id: UUID
    quantity: int = Field(gt=0, le=1_000_000)

    _normalize_sku = field_validator("sku", mode="before")(normalize_upper)


class BatchReservationCreate(APIModel):
    # Only a scope-gated caller (inventory:checkout) or admin can reach
    # this endpoint -- never the buyer's own JWT -- so principal.subject is
    # always the calling service's fixed identity, not the buyer. The
    # buyer this reservation is actually for has to travel in the body
    # instead, same pattern as cart-service's MarkCheckedOutRequest.
    # Unlike that case, Inventory has no pre-existing row to verify this
    # against on a create, so it's taken on faith -- inventory:checkout
    # scope is the entire trust boundary here.
    customer_id: UUID
    cart_reference: str | None = Field(default=None, max_length=120)
    order_reference: str | None = Field(default=None, max_length=120)
    expires_at: AwareDatetime | None = None
    lines: list[BatchReservationLine] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_lines(self) -> Self:
        seen = {(line.seller_id, line.sku) for line in self.lines}
        if len(seen) != len(self.lines):
            raise ValueError(
                "Each (seller_id, sku) pair must appear at most once per batch"
            )
        return self


class ReservationGroupResponse(APIModel):
    reservation_group_id: UUID
    reservation_ids: list[UUID]
    status: ReservationStatus
    expires_at: datetime

    @classmethod
    def from_reservations(cls, group_id: UUID, reservations: list) -> Self:
        return cls(
            reservation_group_id=group_id,
            reservation_ids=[reservation.id for reservation in reservations],
            status=(
                reservations[0].status
                if len({reservation.status for reservation in reservations}) == 1
                else ReservationStatus.ACTIVE
            ),
            expires_at=reservations[0].expires_at,
        )


class MovementResponse(APIModel):
    id: UUID
    inventory_item_id: UUID
    movement_type: MovementType
    reason: MovementReason
    on_hand_delta: int
    reserved_delta: int
    resulting_on_hand: int
    resulting_reserved: int
    reference_type: str | None
    reference_id: str | None
    actor_id: UUID
    note: str | None
    created_at: datetime
