from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import Field, HttpUrl, field_validator, model_validator

from app.models.catalog import ProductStatus
from app.schemas.common import APIModel

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


def normalize_slug(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


class CategoryCreate(APIModel):
    parent_id: UUID | None = None
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=140, pattern=SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=3000)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=100000)

    _normalize_slug = field_validator("slug", mode="before")(normalize_slug)


class CategoryUpdate(APIModel):
    parent_id: UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=140,
        pattern=SLUG_PATTERN,
    )
    description: str | None = Field(default=None, max_length=3000)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)

    _normalize_slug = field_validator("slug", mode="before")(normalize_slug)

    @model_validator(mode="after")
    def non_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one category field must be provided")
        return self


class CategoryResponse(APIModel):
    id: UUID
    parent_id: UUID | None
    name: str
    slug: str
    description: str | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime
    version: int


class VariantCreate(APIModel):
    sku: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    name: str = Field(min_length=1, max_length=200)
    price_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    compare_at_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    currency_code: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )
    attributes: dict[str, Any] = Field(default_factory=dict)
    barcode: str | None = Field(default=None, max_length=80)
    weight_grams: int | None = Field(default=None, ge=0, le=10000000)
    is_active: bool = True

    @field_validator("sku", mode="before")
    @classmethod
    def normalize_sku(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("currency_code", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_compare_price(self) -> Self:
        if (
            self.compare_at_price is not None
            and self.compare_at_price < self.price_amount
        ):
            raise ValueError("compare_at_price must be at least price_amount")
        return self


class VariantUpdate(APIModel):
    sku: str | None = Field(
        default=None,
        min_length=2,
        max_length=80,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    compare_at_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    currency_code: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )
    attributes: dict[str, Any] | None = None
    barcode: str | None = Field(default=None, max_length=80)
    weight_grams: int | None = Field(default=None, ge=0, le=10000000)
    is_active: bool | None = None

    @field_validator("sku", "currency_code", mode="before")
    @classmethod
    def normalize_codes(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def non_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one variant field must be provided")
        return self


class VariantResponse(APIModel):
    id: UUID
    product_id: UUID
    sku: str
    name: str
    price_amount: Decimal
    compare_at_price: Decimal | None
    currency_code: str
    attributes: dict[str, Any]
    barcode: str | None
    weight_grams: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int


class ImageCreate(APIModel):
    url: HttpUrl
    alt_text: str | None = Field(default=None, max_length=300)
    sort_order: int = Field(default=0, ge=0, le=1000)


class ImageResponse(APIModel):
    id: UUID
    product_id: UUID
    url: str
    alt_text: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ProductCreate(APIModel):
    category_id: UUID
    name: str = Field(min_length=2, max_length=240)
    slug: str = Field(min_length=2, max_length=260, pattern=SLUG_PATTERN)
    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    brand: str | None = Field(default=None, max_length=160)
    attributes: dict[str, Any] = Field(default_factory=dict)
    variants: list[VariantCreate] = Field(default_factory=list, max_length=100)
    images: list[ImageCreate] = Field(default_factory=list, max_length=20)

    _normalize_slug = field_validator("slug", mode="before")(normalize_slug)

    @model_validator(mode="after")
    def unique_nested_values(self) -> Self:
        skus = [variant.sku for variant in self.variants]
        if len(skus) != len(set(skus)):
            raise ValueError("Variant SKUs must be unique")
        orders = [image.sort_order for image in self.images]
        if len(orders) != len(set(orders)):
            raise ValueError("Image sort_order values must be unique")
        return self


class ProductUpdate(APIModel):
    category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=240)
    slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=260,
        pattern=SLUG_PATTERN,
    )
    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=20000)
    brand: str | None = Field(default=None, max_length=160)
    attributes: dict[str, Any] | None = None

    _normalize_slug = field_validator("slug", mode="before")(normalize_slug)

    @model_validator(mode="after")
    def non_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one product field must be provided")
        return self


class ProductStatusUpdate(APIModel):
    status: ProductStatus


class ProductSummary(APIModel):
    id: UUID
    owner_user_id: UUID
    category_id: UUID
    name: str
    slug: str
    short_description: str | None
    brand: str | None
    status: ProductStatus
    created_at: datetime
    updated_at: datetime
    version: int


class ProductResponse(ProductSummary):
    description: str | None
    attributes: dict[str, Any]
    variants: list[VariantResponse] = Field(default_factory=list)
    images: list[ImageResponse] = Field(default_factory=list)
