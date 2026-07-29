import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dependencies.auth import Principal
from app.exceptions import ServiceError
from app.models.inventory import (
    CatalogSku,
    InventoryItem,
    InventoryMovement,
    InventoryReservation,
    MovementReason,
    MovementType,
    ReservationStatus,
    Warehouse,
)
from app.models.reliability import AuditLog, IdempotencyRecord, OutboxEvent
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.inventory import (
    CatalogSkuSync,
    InventoryItemCreate,
    InventoryItemUpdate,
    ReservationCreate,
    StockAdjustment,
    WarehouseCreate,
    WarehouseUpdate,
)


class InventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = InventoryRepository(session)
        self.settings = get_settings()

    @staticmethod
    def _snapshot(obj: Any) -> dict:
        return {
            column.name: jsonable_encoder(getattr(obj, column.name))
            for column in obj.__table__.columns
        }

    @staticmethod
    def _can_manage(item: InventoryItem, principal: Principal) -> bool:
        return principal.has_role("admin") or item.seller_id == principal.subject

    def _audit(
        self,
        *,
        principal: Principal,
        action: str,
        resource_type: str,
        resource_id: UUID,
        before: dict | None,
        after: dict | None,
        request_id: str | None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=principal.subject,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                before_data=before,
                after_data=after,
                request_id=request_id,
            )
        )

    def _event(
        self,
        event_type: str,
        item: InventoryItem,
        *,
        reservation: InventoryReservation | None = None,
    ) -> None:
        payload = {
            "event_version": 1,
            "inventory_item_id": str(item.id),
            "warehouse_id": str(item.warehouse_id),
            "product_id": str(item.product_id),
            "variant_id": str(item.variant_id),
            "seller_id": str(item.seller_id),
            "sku": item.sku,
            "on_hand_quantity": item.on_hand_quantity,
            "reserved_quantity": item.reserved_quantity,
            "available_quantity": item.available_quantity,
            "version": item.version,
        }
        if reservation:
            payload.update(
                {
                    "reservation_id": str(reservation.id),
                    "customer_id": str(reservation.customer_id),
                    "reservation_status": reservation.status.value,
                    "quantity": reservation.quantity,
                    "cart_reference": reservation.cart_reference,
                    "order_reference": reservation.order_reference,
                    "expires_at": reservation.expires_at.isoformat(),
                }
            )
        self.session.add(
            OutboxEvent(
                aggregate_type="inventory_item",
                aggregate_id=item.id,
                event_type=event_type,
                payload=payload,
            )
        )

    def _movement(
        self,
        *,
        item: InventoryItem,
        principal: Principal,
        movement_type: MovementType,
        reason: MovementReason,
        on_hand_delta: int = 0,
        reserved_delta: int = 0,
        reference_type: str | None = None,
        reference_id: str | None = None,
        note: str | None = None,
    ) -> None:
        self.session.add(
            InventoryMovement(
                inventory_item_id=item.id,
                movement_type=movement_type,
                reason=reason,
                on_hand_delta=on_hand_delta,
                reserved_delta=reserved_delta,
                resulting_on_hand=item.on_hand_quantity,
                resulting_reserved=item.reserved_quantity,
                reference_type=reference_type,
                reference_id=reference_id,
                actor_id=principal.subject,
                note=note,
                created_at=datetime.now(UTC),
            )
        )

    async def create_warehouse(
        self,
        data: WarehouseCreate,
        principal: Principal,
        request_id: str | None,
    ) -> Warehouse:
        warehouse = Warehouse(**data.model_dump())
        self.session.add(warehouse)
        await self.session.flush()
        self._audit(
            principal=principal,
            action="warehouse.created",
            resource_type="warehouse",
            resource_id=warehouse.id,
            before=None,
            after=self._snapshot(warehouse),
            request_id=request_id,
        )
        await self.session.commit()
        await self.session.refresh(warehouse)
        return warehouse

    async def sync_catalog_sku(
        self,
        data: CatalogSkuSync,
        principal: Principal,
        request_id: str | None,
    ) -> CatalogSku:
        projection = await self.repo.get_catalog_sku(
            data.variant_id,
            for_update=True,
        )
        before = self._snapshot(projection) if projection else None
        if projection:
            projection.product_id = data.product_id
            projection.seller_id = data.seller_id
            projection.sku = data.sku
            projection.is_active = data.is_active
            projection.version += 1
        else:
            projection = CatalogSku(**data.model_dump())
            self.session.add(projection)
        await self.session.flush()
        self._audit(
            principal=principal,
            action="catalog_sku.synced",
            resource_type="catalog_sku",
            resource_id=projection.variant_id,
            before=before,
            after=self._snapshot(projection),
            request_id=request_id,
        )
        await self.session.commit()
        await self.session.refresh(projection)
        return projection

    async def update_warehouse(
        self,
        warehouse_id: UUID,
        data: WarehouseUpdate,
        expected_version: int,
        principal: Principal,
        request_id: str | None,
    ) -> Warehouse:
        warehouse = await self.repo.get_warehouse(warehouse_id, for_update=True)
        if not warehouse:
            raise ServiceError(404, "warehouse_not_found", "Warehouse was not found")
        self._check_version(warehouse, expected_version)
        before = self._snapshot(warehouse)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(warehouse, field, value)
        warehouse.version += 1
        await self.session.flush()
        self._audit(
            principal=principal,
            action="warehouse.updated",
            resource_type="warehouse",
            resource_id=warehouse.id,
            before=before,
            after=self._snapshot(warehouse),
            request_id=request_id,
        )
        await self.session.commit()
        await self.session.refresh(warehouse)
        return warehouse

    async def create_item(
        self,
        data: InventoryItemCreate,
        principal: Principal,
        request_id: str | None,
        idempotency_key: str | None,
    ) -> InventoryItem:
        request_hash = hashlib.sha256(
            data.model_dump_json().encode("utf-8")
        ).hexdigest()
        existing = await self._idempotency_lookup(
            principal,
            idempotency_key,
            request_hash,
        )
        if existing and existing.resource_id:
            item = await self.repo.get_item(existing.resource_id)
            if item:
                return item

        warehouse = await self.repo.get_warehouse(data.warehouse_id)
        if not warehouse or not warehouse.is_active:
            raise ServiceError(
                422,
                "invalid_warehouse",
                "An active warehouse was not found",
            )
        catalog_sku = await self.repo.get_catalog_sku(data.variant_id)
        if (
            not catalog_sku
            or not catalog_sku.is_active
            or catalog_sku.product_id != data.product_id
            or catalog_sku.sku != data.sku
        ):
            raise ServiceError(
                422,
                "invalid_catalog_sku",
                "An active matching Product Service SKU projection was not found",
            )
        if (
            not principal.has_role("admin")
            and catalog_sku.seller_id != principal.subject
        ):
            raise ServiceError(
                403,
                "catalog_sku_forbidden",
                "SKU belongs to another seller",
            )
        values = data.model_dump(exclude={"initial_quantity"})
        item = InventoryItem(
            seller_id=principal.subject,
            on_hand_quantity=data.initial_quantity,
            reserved_quantity=0,
            **values,
        )
        self.session.add(item)
        await self.session.flush()
        if data.initial_quantity:
            self._movement(
                item=item,
                principal=principal,
                movement_type=MovementType.RECEIPT,
                reason=MovementReason.PURCHASE_RECEIPT,
                on_hand_delta=data.initial_quantity,
                reference_type="inventory_item",
                reference_id=str(item.id),
                note="Initial stock",
            )
        self._audit(
            principal=principal,
            action="inventory_item.created",
            resource_type="inventory_item",
            resource_id=item.id,
            before=None,
            after=self._snapshot(item),
            request_id=request_id,
        )
        self._event("inventory.item.created.v1", item)
        if idempotency_key:
            self.session.add(
                IdempotencyRecord(
                    actor_id=principal.subject,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    resource_type="inventory_item",
                    resource_id=item.id,
                )
            )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def update_item(
        self,
        item_id: UUID,
        data: InventoryItemUpdate,
        expected_version: int,
        principal: Principal,
        request_id: str | None,
    ) -> InventoryItem:
        item = await self._managed_item(item_id, principal, for_update=True)
        self._check_version(item, expected_version)
        before = self._snapshot(item)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        item.version += 1
        await self.session.flush()
        self._audit(
            principal=principal,
            action="inventory_item.updated",
            resource_type="inventory_item",
            resource_id=item.id,
            before=before,
            after=self._snapshot(item),
            request_id=request_id,
        )
        self._event("inventory.item.updated.v1", item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def adjust_stock(
        self,
        item_id: UUID,
        data: StockAdjustment,
        expected_version: int,
        principal: Principal,
        request_id: str | None,
        idempotency_key: str | None,
    ) -> InventoryItem:
        request_hash = hashlib.sha256(
            f"{item_id}:{data.model_dump_json()}:{expected_version}".encode()
        ).hexdigest()
        existing = await self._idempotency_lookup(
            principal,
            idempotency_key,
            request_hash,
        )
        if existing:
            item = await self.repo.get_item(item_id)
            if item:
                return item

        item = await self._managed_item(item_id, principal, for_update=True)
        self._check_version(item, expected_version)
        resulting_on_hand = item.on_hand_quantity + data.quantity_delta
        if resulting_on_hand < item.reserved_quantity:
            raise ServiceError(
                409,
                "insufficient_unreserved_stock",
                "Adjustment would reduce stock below the reserved quantity",
            )
        before = self._snapshot(item)
        item.on_hand_quantity = resulting_on_hand
        item.version += 1
        self._movement(
            item=item,
            principal=principal,
            movement_type=MovementType.ADJUSTMENT,
            reason=data.reason,
            on_hand_delta=data.quantity_delta,
            reference_type=data.reference_type,
            reference_id=data.reference_id,
            note=data.note,
        )
        self._audit(
            principal=principal,
            action="stock.adjusted",
            resource_type="inventory_item",
            resource_id=item.id,
            before=before,
            after=self._snapshot(item),
            request_id=request_id,
        )
        self._event("inventory.stock.adjusted.v1", item)
        self._add_low_stock_event_if_needed(item)
        if idempotency_key:
            self.session.add(
                IdempotencyRecord(
                    actor_id=principal.subject,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    resource_type="stock_adjustment",
                    resource_id=item.id,
                )
            )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def create_reservation(
        self,
        data: ReservationCreate,
        principal: Principal,
        request_id: str | None,
        idempotency_key: str | None,
    ) -> InventoryReservation:
        request_hash = hashlib.sha256(
            data.model_dump_json().encode("utf-8")
        ).hexdigest()
        existing = await self._idempotency_lookup(
            principal,
            idempotency_key,
            request_hash,
        )
        if existing and existing.resource_id:
            reservation = await self.repo.get_reservation(existing.resource_id)
            if reservation:
                return reservation

        item = await self.repo.get_item(data.inventory_item_id, for_update=True)
        if not item or not item.is_active:
            raise ServiceError(
                404,
                "inventory_item_not_found",
                "Active inventory item was not found",
            )
        if item.available_quantity < data.quantity:
            raise ServiceError(
                409,
                "insufficient_stock",
                f"Only {item.available_quantity} units are available",
            )
        now = datetime.now(UTC)
        expires_at = data.expires_at or (
            now + timedelta(minutes=self.settings.default_reservation_minutes)
        )
        if expires_at <= now:
            raise ServiceError(
                422,
                "invalid_expiration",
                "Reservation expiration must be in the future",
            )
        maximum = now + timedelta(minutes=self.settings.max_reservation_minutes)
        if expires_at > maximum:
            raise ServiceError(
                422,
                "invalid_expiration",
                "Reservation expiration exceeds the configured maximum",
            )
        before = self._snapshot(item)
        item.reserved_quantity += data.quantity
        item.version += 1
        reservation = InventoryReservation(
            inventory_item_id=item.id,
            customer_id=principal.subject,
            cart_reference=data.cart_reference,
            quantity=data.quantity,
            expires_at=expires_at,
        )
        self.session.add(reservation)
        await self.session.flush()
        self._movement(
            item=item,
            principal=principal,
            movement_type=MovementType.RESERVATION,
            reason=MovementReason.CUSTOMER_ORDER,
            reserved_delta=data.quantity,
            reference_type="reservation",
            reference_id=str(reservation.id),
        )
        self._audit(
            principal=principal,
            action="reservation.created",
            resource_type="inventory_reservation",
            resource_id=reservation.id,
            before=None,
            after=self._snapshot(reservation),
            request_id=request_id,
        )
        self._audit(
            principal=principal,
            action="stock.reserved",
            resource_type="inventory_item",
            resource_id=item.id,
            before=before,
            after=self._snapshot(item),
            request_id=request_id,
        )
        self._event("inventory.reservation.created.v1", item, reservation=reservation)
        self._add_low_stock_event_if_needed(item)
        if idempotency_key:
            self.session.add(
                IdempotencyRecord(
                    actor_id=principal.subject,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    resource_type="inventory_reservation",
                    resource_id=reservation.id,
                )
            )
        await self.session.commit()
        await self.session.refresh(reservation)
        return reservation

    async def commit_reservation(
        self,
        reservation_id: UUID,
        order_reference: str,
        principal: Principal,
        request_id: str | None,
    ) -> InventoryReservation:
        reservation, item = await self._active_reservation_with_item(
            reservation_id,
            principal,
        )
        now = datetime.now(UTC)
        if reservation.expires_at <= now:
            await self._resolve_reservation(
                reservation=reservation,
                item=item,
                principal=principal,
                target=ReservationStatus.EXPIRED,
                reason=MovementReason.RESERVATION_EXPIRED,
                request_id=request_id,
            )
            await self.session.commit()
            raise ServiceError(
                409,
                "reservation_expired",
                "Reservation expired before it could be committed",
            )
        before_item = self._snapshot(item)
        before_reservation = self._snapshot(reservation)
        item.reserved_quantity -= reservation.quantity
        item.on_hand_quantity -= reservation.quantity
        item.version += 1
        reservation.status = ReservationStatus.COMMITTED
        reservation.order_reference = order_reference
        reservation.resolved_at = now
        reservation.version += 1
        self._movement(
            item=item,
            principal=principal,
            movement_type=MovementType.COMMITMENT,
            reason=MovementReason.CUSTOMER_ORDER,
            on_hand_delta=-reservation.quantity,
            reserved_delta=-reservation.quantity,
            reference_type="order",
            reference_id=order_reference,
        )
        self._audit_resolution(
            principal,
            reservation,
            item,
            before_reservation,
            before_item,
            "reservation.committed",
            request_id,
        )
        self._event("inventory.reservation.committed.v1", item, reservation=reservation)
        await self.session.commit()
        await self.session.refresh(reservation)
        return reservation

    async def release_reservation(
        self,
        reservation_id: UUID,
        reason: MovementReason,
        note: str | None,
        principal: Principal,
        request_id: str | None,
    ) -> InventoryReservation:
        reservation, item = await self._active_reservation_with_item(
            reservation_id,
            principal,
        )
        await self._resolve_reservation(
            reservation=reservation,
            item=item,
            principal=principal,
            target=ReservationStatus.RELEASED,
            reason=reason,
            request_id=request_id,
            note=note,
        )
        await self.session.commit()
        await self.session.refresh(reservation)
        return reservation

    async def expire_reservations(
        self,
        principal: Principal,
        request_id: str | None,
        limit: int = 100,
    ) -> int:
        reservations = await self.repo.list_expired_active(
            datetime.now(UTC),
            limit=limit,
        )
        count = 0
        for reservation in reservations:
            item = await self.repo.get_item(
                reservation.inventory_item_id,
                for_update=True,
            )
            if not item:
                continue
            await self._resolve_reservation(
                reservation=reservation,
                item=item,
                principal=principal,
                target=ReservationStatus.EXPIRED,
                reason=MovementReason.RESERVATION_EXPIRED,
                request_id=request_id,
            )
            count += 1
        await self.session.commit()
        return count

    async def _active_reservation_with_item(
        self,
        reservation_id: UUID,
        principal: Principal,
    ) -> tuple[InventoryReservation, InventoryItem]:
        reservation = await self.repo.get_reservation(
            reservation_id,
            for_update=True,
        )
        if not reservation:
            raise ServiceError(
                404,
                "reservation_not_found",
                "Reservation was not found",
            )
        if (
            not principal.has_role("admin", "seller")
            and reservation.customer_id != principal.subject
            and not principal.has_scope("inventory:commit")
        ):
            raise ServiceError(
                403,
                "reservation_forbidden",
                "Reservation belongs to another customer",
            )
        if reservation.status != ReservationStatus.ACTIVE:
            raise ServiceError(
                409,
                "reservation_not_active",
                f"Reservation is already {reservation.status.value}",
            )
        item = await self.repo.get_item(
            reservation.inventory_item_id,
            for_update=True,
        )
        if not item:
            raise ServiceError(
                409,
                "inventory_item_missing",
                "Reserved inventory item no longer exists",
            )
        return reservation, item

    async def _resolve_reservation(
        self,
        *,
        reservation: InventoryReservation,
        item: InventoryItem,
        principal: Principal,
        target: ReservationStatus,
        reason: MovementReason,
        request_id: str | None,
        note: str | None = None,
    ) -> None:
        before_item = self._snapshot(item)
        before_reservation = self._snapshot(reservation)
        item.reserved_quantity -= reservation.quantity
        item.version += 1
        reservation.status = target
        reservation.resolved_at = datetime.now(UTC)
        reservation.version += 1
        self._movement(
            item=item,
            principal=principal,
            movement_type=MovementType.RELEASE,
            reason=reason,
            reserved_delta=-reservation.quantity,
            reference_type="reservation",
            reference_id=str(reservation.id),
            note=note,
        )
        self._audit_resolution(
            principal,
            reservation,
            item,
            before_reservation,
            before_item,
            f"reservation.{target.value}",
            request_id,
        )
        self._event(
            f"inventory.reservation.{target.value}.v1",
            item,
            reservation=reservation,
        )

    def _audit_resolution(
        self,
        principal: Principal,
        reservation: InventoryReservation,
        item: InventoryItem,
        before_reservation: dict,
        before_item: dict,
        action: str,
        request_id: str | None,
    ) -> None:
        self._audit(
            principal=principal,
            action=action,
            resource_type="inventory_reservation",
            resource_id=reservation.id,
            before=before_reservation,
            after=self._snapshot(reservation),
            request_id=request_id,
        )
        self._audit(
            principal=principal,
            action="stock.changed",
            resource_type="inventory_item",
            resource_id=item.id,
            before=before_item,
            after=self._snapshot(item),
            request_id=request_id,
        )

    async def _managed_item(
        self,
        item_id: UUID,
        principal: Principal,
        *,
        for_update: bool = False,
    ) -> InventoryItem:
        item = await self.repo.get_item(item_id, for_update=for_update)
        if not item:
            raise ServiceError(
                404,
                "inventory_item_not_found",
                "Inventory item was not found",
            )
        if not self._can_manage(item, principal):
            raise ServiceError(
                403,
                "inventory_forbidden",
                "Inventory item belongs to another seller",
            )
        return item

    async def _idempotency_lookup(
        self,
        principal: Principal,
        idempotency_key: str | None,
        request_hash: str,
    ) -> IdempotencyRecord | None:
        if not idempotency_key:
            return None
        existing = await self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.actor_id == principal.subject,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if existing and existing.request_hash != request_hash:
            raise ServiceError(
                409,
                "idempotency_conflict",
                "Idempotency key was reused with another request",
            )
        return existing

    def _add_low_stock_event_if_needed(self, item: InventoryItem) -> None:
        if item.available_quantity <= item.low_stock_threshold:
            self._event("inventory.stock.low.v1", item)

    @staticmethod
    def _check_version(resource: Any, expected: int) -> None:
        if resource.version != expected:
            raise ServiceError(412, "version_conflict", "Resource version has changed")
