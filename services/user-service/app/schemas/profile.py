from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import EmailStr, Field, field_validator, model_validator

from app.models.profile import ProfileStatus, SellerStatus
from app.schemas.common import APIModel


class BuyerProfileCreate(APIModel):
    display_name: str = Field(min_length=2, max_length=100)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone_number: str | None = Field(default=None, max_length=32)
    profile_image_reference: str | None = Field(default=None, max_length=512)


class BuyerProfileUpdate(APIModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=100)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone_number: str | None = Field(default=None, max_length=32)
    profile_image_reference: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one profile field must be provided")
        return self


class SellerProfileCreate(APIModel):
    business_name: str = Field(min_length=2, max_length=200)
    store_slug: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = Field(default=None, max_length=5000)
    support_email: EmailStr | None = None
    support_phone: str | None = Field(default=None, max_length=32)

    @field_validator("store_slug", mode="before")
    @classmethod
    def slug(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class SellerProfileUpdate(APIModel):
    business_name: str | None = Field(default=None, min_length=2, max_length=200)
    store_slug: str | None = Field(
        default=None, min_length=3, max_length=100, pattern=r"^[a-z0-9-]+$"
    )
    description: str | None = Field(default=None, max_length=5000)
    support_email: EmailStr | None = None
    support_phone: str | None = Field(default=None, max_length=32)

    @field_validator("store_slug", mode="before")
    @classmethod
    def slug(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one seller field must be provided")
        return self


class SellerProfileResponse(APIModel):
    id: UUID
    buyer_profile_id: UUID
    business_name: str
    store_slug: str
    description: str | None
    support_email: str | None
    support_phone: str | None
    status: SellerStatus
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class PublicSellerProfile(APIModel):
    id: UUID
    business_name: str
    store_slug: str
    description: str | None
    status: SellerStatus


class BuyerProfileResponse(APIModel):
    id: UUID
    user_id: UUID
    display_name: str
    first_name: str | None
    last_name: str | None
    phone_number: str | None
    profile_image_reference: str | None
    status: ProfileStatus
    deactivated_at: datetime | None
    is_profile_complete: bool
    seller_profile: SellerProfileResponse | None = None
    created_at: datetime
    updated_at: datetime
    version: int
