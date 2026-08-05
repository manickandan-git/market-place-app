from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.models.shipment import ShipmentStatus
from app.schemas.common import APIModel


class ShipmentCreate(APIModel):
    order_id: UUID
    carrier: str = Field(min_length=1, max_length=80)
    service_level: str | None = Field(default=None, max_length=80)


class ShipmentShip(APIModel):
    tracking_number: str = Field(min_length=1, max_length=160)
    carrier: str | None = Field(default=None, min_length=1, max_length=80)
    occurred_at: AwareDatetime | None = None


class ShipmentDeliver(APIModel):
    occurred_at: AwareDatetime | None = None


class ShipmentException(APIModel):
    reason: str = Field(min_length=1, max_length=280)
    occurred_at: AwareDatetime | None = None


class ShipmentEventResponse(APIModel):
    id: UUID
    event_type: str
    description: str | None
    occurred_at: datetime


class ShipmentResponse(APIModel):
    id: UUID
    order_id: UUID
    seller_id: UUID
    carrier: str
    service_level: str | None
    tracking_number: str | None
    status: ShipmentStatus
    failure_reason: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    events: list[ShipmentEventResponse]
