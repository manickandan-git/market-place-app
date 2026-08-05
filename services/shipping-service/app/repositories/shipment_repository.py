from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reliability import IdempotencyRecord
from app.models.shipment import Shipment


class ShipmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_shipment(
        self,
        shipment_id: UUID,
        *,
        for_update: bool = False,
    ) -> Shipment | None:
        stmt = select(Shipment).where(Shipment.id == shipment_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).unique().one_or_none()

    async def get_by_order(
        self,
        order_id: UUID,
        *,
        for_update: bool = False,
    ) -> Shipment | None:
        stmt = select(Shipment).where(Shipment.order_id == order_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).unique().one_or_none()

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
