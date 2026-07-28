from datetime import datetime
from typing import Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from app.models.preferences import NotificationCategory, NotificationChannel
from app.schemas.common import APIModel


class UserPreferenceUpdate(APIModel):
    language_code: str | None = Field(default=None, min_length=2, max_length=35)
    time_zone: str | None = Field(default=None, min_length=3, max_length=64)
    currency_code: str | None = Field(
        default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$"
    )
    marketplace_code: str | None = Field(
        default=None, min_length=2, max_length=2, pattern=r"^[A-Z]{2}$"
    )

    @field_validator("currency_code", "marketplace_code", mode="before")
    @classmethod
    def upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("time_zone")
    @classmethod
    def timezone(cls, value: str | None) -> str | None:
        if value:
            try:
                ZoneInfo(value)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("Invalid IANA time zone") from exc
        return value

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one preference field must be provided")
        return self


class UserPreferenceResponse(APIModel):
    id: UUID
    buyer_profile_id: UUID
    language_code: str
    time_zone: str
    currency_code: str
    marketplace_code: str
    created_at: datetime
    updated_at: datetime
    version: int


class NotificationPreferenceItem(APIModel):
    channel: NotificationChannel
    category: NotificationCategory
    is_enabled: bool


class NotificationPreferencesUpdate(APIModel):
    preferences: list[NotificationPreferenceItem] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique(self) -> Self:
        keys = [(item.channel, item.category) for item in self.preferences]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate notification preference")
        return self


class NotificationPreferenceResponse(NotificationPreferenceItem):
    id: UUID
    buyer_profile_id: UUID
    created_at: datetime
    updated_at: datetime
    version: int
