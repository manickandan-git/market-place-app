from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, Refund
from app.models.reliability import IdempotencyRecord, WebhookEvent


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_payment(
        self,
        payment_id: UUID,
        *,
        for_update: bool = False,
    ) -> Payment | None:
        stmt = select(Payment).where(Payment.id == payment_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).one_or_none()

    async def get_payment_by_order(
        self,
        order_id: UUID,
        *,
        for_update: bool = False,
    ) -> Payment | None:
        stmt = select(Payment).where(Payment.order_id == order_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).one_or_none()

    async def get_payment_by_intent(
        self,
        provider_payment_intent_id: str,
        *,
        for_update: bool = False,
    ) -> Payment | None:
        stmt = select(Payment).where(
            Payment.provider_payment_intent_id == provider_payment_intent_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).one_or_none()

    async def get_refund(self, refund_id: UUID) -> Refund | None:
        stmt = select(Refund).where(Refund.id == refund_id)
        return await self.session.scalar(stmt)

    async def list_refunds(self, payment_id: UUID) -> list[Refund]:
        stmt = (
            select(Refund)
            .where(Refund.payment_id == payment_id)
            .order_by(Refund.created_at)
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_webhook_event(
        self,
        provider_event_id: str,
    ) -> WebhookEvent | None:
        stmt = select(WebhookEvent).where(
            WebhookEvent.provider_event_id == provider_event_id
        )
        return await self.session.scalar(stmt)

    async def get_idempotency_record(
        self,
        actor_id: UUID,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        stmt = select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
        return await self.session.scalar(stmt)
