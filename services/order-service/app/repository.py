from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdempotencyRecord, Order


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, order_id: UUID, *, lock: bool = False) -> Order | None:
        statement = select(Order).where(Order.id == order_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def by_number(self, order_number: str) -> Order | None:
        return await self.session.scalar(
            select(Order).where(Order.order_number == order_number)
        )

    async def by_customer_cart(self, customer_id: UUID, cart_id: UUID) -> Order | None:
        return await self.session.scalar(
            select(Order).where(
                Order.customer_id == customer_id, Order.cart_id == cart_id
            )
        )

    async def list_for_customer(
        self, customer_id: UUID, page: int, page_size: int
    ) -> tuple[list[Order], int]:
        condition = Order.customer_id == customer_id
        total = int(
            await self.session.scalar(
                select(func.count()).select_from(Order).where(condition)
            )
            or 0
        )
        rows = await self.session.scalars(
            select(Order)
            .where(condition)
            .order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.unique()), total

    async def idempotency(self, actor_id: str, key: str) -> IdempotencyRecord | None:
        return await self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.actor_id == actor_id,
                IdempotencyRecord.key == key,
            )
        )
