from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cart import Cart, CartItem, CartStatus, SavedItem
from app.models.reliability import IdempotencyRecord


class CartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _cart_query():
        return select(Cart).options(
            selectinload(Cart.items), selectinload(Cart.saved_items)
        )

    async def get(self, cart_id: UUID, *, for_update: bool = False) -> Cart | None:
        query = self._cart_query().where(Cart.id == cart_id)
        if for_update:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_active_customer_cart(
        self, customer_id: UUID, *, for_update: bool = False
    ) -> Cart | None:
        query = self._cart_query().where(
            Cart.customer_id == customer_id, Cart.status == CartStatus.ACTIVE
        )
        if for_update:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_guest_cart(
        self, token_hash: str, *, for_update: bool = False
    ) -> Cart | None:
        query = self._cart_query().where(
            Cart.guest_token_hash == token_hash, Cart.status == CartStatus.ACTIVE
        )
        if for_update:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_item(self, cart_id: UUID, item_id: UUID) -> CartItem | None:
        return (
            await self.session.execute(
                select(CartItem).where(
                    CartItem.cart_id == cart_id, CartItem.id == item_id
                )
            )
        ).scalar_one_or_none()

    async def get_saved_item(self, cart_id: UUID, item_id: UUID) -> SavedItem | None:
        return (
            await self.session.execute(
                select(SavedItem).where(
                    SavedItem.cart_id == cart_id, SavedItem.id == item_id
                )
            )
        ).scalar_one_or_none()

    async def get_idempotency(
        self, actor_key: str, key: str
    ) -> IdempotencyRecord | None:
        return (
            await self.session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.actor_key == actor_key,
                    IdempotencyRecord.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()

    async def expire_due(self) -> int:
        carts = (
            await self.session.execute(
                select(Cart).where(
                    Cart.status == CartStatus.ACTIVE,
                    Cart.expires_at <= datetime.now(UTC),
                )
            )
        ).scalars()
        count = 0
        for cart in carts:
            cart.status = CartStatus.EXPIRED
            cart.version += 1
            count += 1
        await self.session.commit()
        return count
