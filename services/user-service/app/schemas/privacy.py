from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.models.privacy import PrivacyRequestStatus, PrivacyRequestType
from app.schemas.common import APIModel


class PrivacyRequestCreate(APIModel):
    request_type: PrivacyRequestType
    request_details: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def correction_details(self) -> Self:
        if self.request_type == PrivacyRequestType.CORRECTION and not self.request_details:
            raise ValueError("request_details is required for correction")
        return self


class PrivacyRequestResponse(APIModel):
    id: UUID
    buyer_profile_id: UUID
    request_type: PrivacyRequestType
    status: PrivacyRequestStatus
    request_details: str | None
    due_at: datetime | None
    resolved_at: datetime | None
    resolution_notes: str | None
    result_reference: str | None
    result_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
