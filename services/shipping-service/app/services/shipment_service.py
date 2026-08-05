from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dependencies.auth import Principal
from app.exceptions import ServiceError
from app.models.reliability import IdempotencyRecord
from app.models.shipment import Shipment, ShipmentEvent, ShipmentStatus
from app.repositories.shipment_repository import ShipmentRepository
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentDeliver,
    ShipmentException,
    ShipmentShip,
)
from app.services.auth_client import AuthClient
from app.services.order_client import OrderClient


class ShipmentService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        orders: OrderClient,
        auth: AuthClient,
    ) -> None:
        self.session = session
        self.settings = settings
        self.repo = ShipmentRepository(session)
        self.orders = orders
        self.auth = auth

    async def create_shipment(
        self,
        data: ShipmentCreate,
        principal: Principal,
        idempotency_key: str,
        request_id: str | None,
    ) -> Shipment:
        request_hash = hashlib.sha256(
            data.model_dump_json().encode("utf-8")
        ).hexdigest()
        existing = await self.repo.get_idempotency_record(
            principal.subject, idempotency_key
        )
        if existing:
            if existing.request_hash != request_hash:
                raise ServiceError(
                    409,
                    "idempotency_conflict",
                    "Idempotency key was reused with another request",
                )
            if existing.resource_id:
                shipment = await self.repo.get_shipment(existing.resource_id)
                if shipment:
                    return shipment

        if await self.repo.get_by_order(data.order_id):
            raise ServiceError(
                409,
                "shipment_already_exists",
                "A shipment already exists for this order",
            )

        # Call Order first: if the order isn't confirmed yet (or is already
        # past processing), nothing gets created here either — there's
        # never a local Shipment row that doesn't correspond to a real
        # Order transition.
        token = await self.auth.service_token()
        await self.orders.advance_fulfillment(
            data.order_id, "processing", None, None, token, request_id
        )

        shipment = Shipment(
            order_id=data.order_id,
            seller_id=principal.subject,
            carrier=data.carrier,
            service_level=data.service_level,
            status=ShipmentStatus.PENDING,
        )
        self.session.add(shipment)
        await self.session.flush()
        self.session.add(
            ShipmentEvent(
                shipment_id=shipment.id,
                event_type="created",
                description=f"Shipment booked with {data.carrier}",
                occurred_at=datetime.now(UTC),
            )
        )
        self.session.add(
            IdempotencyRecord(
                actor_id=principal.subject,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                resource_type="shipment",
                resource_id=shipment.id,
            )
        )
        await self.session.commit()
        await self.session.refresh(shipment)
        return shipment

    async def ship(
        self,
        shipment_id: UUID,
        data: ShipmentShip,
        principal: Principal,
        request_id: str | None,
    ) -> Shipment:
        shipment = await self._owned_shipment(shipment_id, principal, for_update=True)
        if shipment.status != ShipmentStatus.PENDING:
            raise ServiceError(
                409,
                "shipment_not_pending",
                f"Shipment is already {shipment.status.value}",
            )

        token = await self.auth.service_token()
        await self.orders.advance_fulfillment(
            shipment.order_id,
            "shipped",
            data.tracking_number,
            data.occurred_at,
            token,
            request_id,
        )

        occurred_at = data.occurred_at or datetime.now(UTC)
        shipment.tracking_number = data.tracking_number
        if data.carrier:
            shipment.carrier = data.carrier
        shipment.status = ShipmentStatus.SHIPPED
        shipment.shipped_at = occurred_at
        shipment.version += 1
        self.session.add(
            ShipmentEvent(
                shipment_id=shipment.id,
                event_type="shipped",
                description=(
                    f"Picked up by {shipment.carrier}, "
                    f"tracking {data.tracking_number}"
                ),
                occurred_at=occurred_at,
            )
        )
        await self.session.commit()
        await self.session.refresh(shipment)
        return shipment

    async def deliver(
        self,
        shipment_id: UUID,
        data: ShipmentDeliver,
        principal: Principal,
        request_id: str | None,
    ) -> Shipment:
        shipment = await self._owned_shipment(shipment_id, principal, for_update=True)
        if shipment.status != ShipmentStatus.SHIPPED:
            raise ServiceError(
                409,
                "shipment_not_shipped",
                f"Shipment is {shipment.status.value}, not shipped",
            )

        token = await self.auth.service_token()
        await self.orders.advance_fulfillment(
            shipment.order_id, "delivered", None, data.occurred_at, token, request_id
        )

        occurred_at = data.occurred_at or datetime.now(UTC)
        shipment.status = ShipmentStatus.DELIVERED
        shipment.delivered_at = occurred_at
        shipment.version += 1
        self.session.add(
            ShipmentEvent(
                shipment_id=shipment.id,
                event_type="delivered",
                description="Delivered",
                occurred_at=occurred_at,
            )
        )
        await self.session.commit()
        await self.session.refresh(shipment)
        return shipment

    async def record_exception(
        self,
        shipment_id: UUID,
        data: ShipmentException,
        principal: Principal,
        request_id: str | None,
    ) -> Shipment:
        """Terminal failure path with no Order callback: Order's fulfillment
        machine only moves forward (processing/shipped/delivered) and has
        no state representing a shipping exception. See
        docs/shipping-service-scope.md."""
        shipment = await self._owned_shipment(shipment_id, principal, for_update=True)
        if shipment.status not in (ShipmentStatus.PENDING, ShipmentStatus.SHIPPED):
            raise ServiceError(
                409,
                "shipment_not_active",
                f"Shipment is already {shipment.status.value}",
            )

        occurred_at = data.occurred_at or datetime.now(UTC)
        shipment.status = ShipmentStatus.FAILED
        shipment.failure_reason = data.reason
        shipment.version += 1
        self.session.add(
            ShipmentEvent(
                shipment_id=shipment.id,
                event_type="exception",
                description=data.reason,
                occurred_at=occurred_at,
            )
        )
        await self.session.commit()
        await self.session.refresh(shipment)
        return shipment

    async def get_shipment(
        self,
        shipment_id: UUID,
        principal: Principal,
    ) -> Shipment:
        return await self._owned_shipment(shipment_id, principal)

    async def get_by_order(
        self,
        order_id: UUID,
        principal: Principal,
    ) -> Shipment:
        shipment = await self.repo.get_by_order(order_id)
        if not shipment or (
            shipment.seller_id != principal.subject and not principal.has_role("admin")
        ):
            raise ServiceError(404, "shipment_not_found", "Shipment was not found")
        return shipment

    async def _owned_shipment(
        self,
        shipment_id: UUID,
        principal: Principal,
        *,
        for_update: bool = False,
    ) -> Shipment:
        shipment = await self.repo.get_shipment(shipment_id, for_update=for_update)
        if not shipment:
            raise ServiceError(404, "shipment_not_found", "Shipment was not found")
        if shipment.seller_id != principal.subject and not principal.has_role("admin"):
            raise ServiceError(404, "shipment_not_found", "Shipment was not found")
        return shipment
