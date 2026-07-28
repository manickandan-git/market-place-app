from __future__ import annotations

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.address import AddressType
from app.schemas.common import APIModel


class AddressCreate(APIModel):
    """Request payload for creating a buyer shipping or billing address."""

    address_type: AddressType
    label: str | None = Field(default=None, max_length=50)
    recipient_name: str = Field(min_length=2, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    address_line1: str = Field(min_length=3, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    state_or_region: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(min_length=3, max_length=32)
    country_code: str = Field(
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
        description="ISO 3166-1 alpha-2 country code",
    )
    phone_number: str | None = Field(default=None, max_length=32)
    delivery_instructions: str | None = Field(
        default=None,
        max_length=2000,
    )
    is_default: bool = False

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: object) -> object:
        """Normalize a country code before validating it."""
        if isinstance(value, str):
            return value.strip().upper()
        return value


class AddressUpdate(APIModel):
    """Request payload for partially updating an address."""

    address_type: AddressType | None = None
    label: str | None = Field(default=None, max_length=50)
    recipient_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
    )
    company_name: str | None = Field(default=None, max_length=200)
    address_line1: str | None = Field(
        default=None,
        min_length=3,
        max_length=200,
    )
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )
    state_or_region: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(
        default=None,
        min_length=3,
        max_length=32,
    )
    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
        description="ISO 3166-1 alpha-2 country code",
    )
    phone_number: str | None = Field(default=None, max_length=32)
    delivery_instructions: str | None = Field(
        default=None,
        max_length=2000,
    )
    is_default: bool | None = None

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: object) -> object:
        """Normalize a country code before validating it."""
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @model_validator(mode="after")
    def ensure_at_least_one_field(self) -> Self:
        """Reject an empty PATCH request."""
        if not self.model_fields_set:
            raise ValueError("At least one address field must be provided")
        return self


class AddressDefaultUpdate(APIModel):
    """Request for making an address the default for its address type."""

    is_default: bool = True


class AddressResponse(APIModel):
    """Address returned by the API."""

    id: UUID
    buyer_profile_id: UUID
    address_type: AddressType
    label: str | None
    recipient_name: str
    company_name: str | None
    address_line1: str
    address_line2: str | None
    city: str
    state_or_region: str | None
    postal_code: str
    country_code: str
    phone_number: str | None
    delivery_instructions: str | None
    is_default: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class AddressSummary(APIModel):
    """Compact address representation for checkout and order workflows."""

    id: UUID
    address_type: AddressType
    label: str | None
    recipient_name: str
    address_line1: str
    address_line2: str | None
    city: str
    state_or_region: str | None
    postal_code: str
    country_code: str
    is_default: bool
