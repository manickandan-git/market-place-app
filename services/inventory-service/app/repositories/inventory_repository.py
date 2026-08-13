from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import (
    CatalogSku,
    InventoryItem,
    InventoryMovement,
    InventoryReservation,
    ReservationStatus,
    Warehouse,
)


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_catalog_sku(
        self,
        variant_id: UUID,
        *,
        for_update: bool = False,
    ) -> CatalogSku | None:
        stmt = select(CatalogSku).where(CatalogSku.variant_id == variant_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).one_or_none()

    async def get_warehouse(
        self,
        warehouse_id: UUID,
        *,
        for_update: bool = False,
    ) -> Warehouse | None:
        stmt = select(Warehouse).where(Warehouse.id == warehouse_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).one_or_none()

    async def list_warehouses(self, active_only: bool = True) -> list[Warehouse]:
        stmt = select(Warehouse).order_by(Warehouse.name)
        if active_only:
            stmt = stmt.where(Warehouse.is_active.is_(True))
        return list((await self.session.scalars(stmt)).all())

    async def get_item(
        self,
        item_id: UUID,
        *,
        for_update: bool = False,
    ) -> InventoryItem | None:
        stmt = select(InventoryItem).where(InventoryItem.id == item_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).one_or_none()

    async def list_items(
        self,
        *,
        page: int,
        page_size: int,
        seller_id: UUID | None = None,
        warehouse_id: UUID | None = None,
        sku: str | None = None,
        low_stock_only: bool = False,
    ) -> tuple[list[InventoryItem], int]:
        filters = []
        if seller_id:
            filters.append(InventoryItem.seller_id == seller_id)
        if warehouse_id:
            filters.append(InventoryItem.warehouse_id == warehouse_id)
        if sku:
            filters.append(InventoryItem.sku == sku)
        if low_stock_only:
            filters.append(
                InventoryItem.on_hand_quantity - InventoryItem.reserved_quantity
                <= InventoryItem.low_stock_threshold
            )
        total = int(
            (
                await self.session.scalar(
                    select(func.count(InventoryItem.id)).where(*filters)
                )
            )
            or 0
        )
        stmt = (
            select(InventoryItem)
            .where(*filters)
            .order_by(InventoryItem.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_availability(self, sku: str) -> int:
        stmt = select(
            func.coalesce(
                func.sum(
                    InventoryItem.on_hand_quantity - InventoryItem.reserved_quantity
                ),
                0,
            )
        ).where(
            InventoryItem.sku == sku,
            InventoryItem.is_active.is_(True),
        )
        return int((await self.session.scalar(stmt)) or 0)

    async def get_reservation(
        self,
        reservation_id: UUID,
        *,
        for_update: bool = False,
    ) -> InventoryReservation | None:
        stmt = select(InventoryReservation).where(
            InventoryReservation.id == reservation_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).one_or_none()

    async def list_reservations(
        self,
        *,
        customer_id: UUID | None,
        status: ReservationStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[InventoryReservation], int]:
        filters = []
        if customer_id:
            filters.append(InventoryReservation.customer_id == customer_id)
        if status:
            filters.append(InventoryReservation.status == status)
        total = int(
            (
                await self.session.scalar(
                    select(func.count(InventoryReservation.id)).where(*filters)
                )
            )
            or 0
        )
        stmt = (
            select(InventoryReservation)
            .where(*filters)
            .order_by(InventoryReservation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def list_expired_active(
        self,
        now: datetime,
        *,
        limit: int = 100,
    ) -> list[InventoryReservation]:
        stmt = (
            select(InventoryReservation)
            .where(
                InventoryReservation.status == ReservationStatus.ACTIVE,
                InventoryReservation.expires_at <= now,
            )
            .order_by(InventoryReservation.expires_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_items_for_reservation(
        self,
        pairs: set[tuple[UUID, str]],
        *,
        for_update: bool = False,
    ) -> list[InventoryItem]:
        if not pairs:
            return []
        seller_ids = {pair[0] for pair in pairs}
        skus = {pair[1] for pair in pairs}
        stmt = (
            select(InventoryItem)
            .where(
                InventoryItem.seller_id.in_(seller_ids),
                InventoryItem.sku.in_(skus),
                InventoryItem.is_active.is_(True),
            )
            .order_by(InventoryItem.id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        rows = (await self.session.scalars(stmt)).all()
        return [row for row in rows if (row.seller_id, row.sku) in pairs]

    async def get_items_by_ids(
        self,
        ids: set[UUID],
        *,
        for_update: bool = False,
    ) -> list[InventoryItem]:
        if not ids:
            return []
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.id.in_(ids))
            .order_by(InventoryItem.id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return list((await self.session.scalars(stmt)).all())

    async def list_reservations_by_group(
        self,
        group_id: UUID,
        *,
        for_update: bool = False,
    ) -> list[InventoryReservation]:
        stmt = (
            select(InventoryReservation)
            .where(InventoryReservation.reservation_group_id == group_id)
            .order_by(InventoryReservation.id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return list((await self.session.scalars(stmt)).all())

    async def list_movements(
        self,
        item_id: UUID,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[InventoryMovement], int]:
        total = int(
            (
                await self.session.scalar(
                    select(func.count(InventoryMovement.id)).where(
                        InventoryMovement.inventory_item_id == item_id
                    )
                )
            )
            or 0
        )
        stmt = (
            select(InventoryMovement)
            .where(InventoryMovement.inventory_item_id == item_id)
            .order_by(InventoryMovement.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total
