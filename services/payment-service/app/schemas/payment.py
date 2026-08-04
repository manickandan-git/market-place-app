from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.models.payment import PaymentStatus, RefundStatus
from app.schemas.common import APIModel


class PaymentCreate(APIModel):
    order_id: UUID


class PaymentResponse(APIModel):
    id: UUID
    order_id: UUID
    customer_id: UUID
    amount: Decimal
    currency_code: str
    provider: str
    provider_payment_intent_id: str
    status: PaymentStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    version: int


class PaymentCreateResponse(APIModel):
    """client_secret is returned once, at creation, and never persisted or
    re-served — the buyer's client must confirm the PaymentIntent with it
    immediately (via Stripe.js) or the payment is re-created."""

    payment: PaymentResponse
    client_secret: str | None


class RefundCreate(APIModel):
    amount: Decimal | None = Field(default=None, gt=0)
    reason: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def non_negative(self) -> Self:
        if self.amount is not None and self.amount <= 0:
            raise ValueError("amount must be greater than zero")
        return self


class RefundResponse(APIModel):
    id: UUID
    payment_id: UUID
    provider_refund_id: str | None
    amount: Decimal
    reason: str | None
    status: RefundStatus
    created_at: datetime
