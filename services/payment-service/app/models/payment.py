from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class PaymentStatus(StrEnum):
    PENDING = "pending"
    REQUIRES_ACTION = "requires_action"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class RefundStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    """One payment attempt per order; owns the Stripe PaymentIntent."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_payments_order_id"),
        UniqueConstraint(
            "provider_payment_intent_id",
            name="uq_payments_provider_payment_intent_id",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_payments_customer", "customer_id"),
    )

    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), default="stripe", nullable=False)
    provider_payment_intent_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)

    # selectin (not the lazy default): refunded_amount reads this
    # synchronously, and a lazy load under AsyncSession would crash with
    # MissingGreenlet the moment it wasn't already loaded.
    refunds: Mapped[list[Refund]] = relationship(
        back_populates="payment", lazy="selectin"
    )

    @property
    def refunded_amount(self) -> Decimal:
        return sum(
            (r.amount for r in self.refunds if r.status == RefundStatus.SUCCEEDED),
            Decimal(0),
        )


class Refund(Base, UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="refund_amount_positive"),
        Index("ix_refunds_payment", "payment_id"),
    )

    payment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_refund_id: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[RefundStatus] = mapped_column(
        Enum(RefundStatus, name="refund_status", native_enum=False),
        default=RefundStatus.PENDING,
        nullable=False,
    )

    payment: Mapped[Payment] = relationship(back_populates="refunds")
