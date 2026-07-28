from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.models.consent import ConsentSource, ConsentType
from app.schemas.common import APIModel


class ConsentDecision(APIModel):
    consent_type: ConsentType
    is_granted: bool
    policy_version: str = Field(min_length=1, max_length=50)
    policy_reference: str | None = Field(default=None, max_length=512)


class ConsentsUpdate(APIModel):
    consents: list[ConsentDecision] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique(self) -> Self:
        values = [item.consent_type for item in self.consents]
        if len(values) != len(set(values)):
            raise ValueError("Duplicate consent type")
        return self


class ConsentResponse(ConsentDecision):
    id: UUID
    buyer_profile_id: UUID
    source: ConsentSource
    decided_at: datetime
    created_at: datetime
    updated_at: datetime
    version: int
