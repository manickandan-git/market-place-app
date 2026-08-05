from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import Principal, require_roles
from app.dependencies.headers import required_idempotency_key
from app.routes.dependencies import get_shipment_service
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentDeliver,
    ShipmentException,
    ShipmentResponse,
    ShipmentShip,
)
from app.services.shipment_service import ShipmentService

router = APIRouter(prefix="/shipments", tags=["shipments"])
SellerOrAdmin = Annotated[Principal, Depends(require_roles("seller", "admin"))]
Service = Annotated[ShipmentService, Depends(get_shipment_service)]
IdempotencyKey = Annotated[str, Depends(required_idempotency_key)]


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post("", response_model=ShipmentResponse, status_code=201)
async def create_shipment(
    data: ShipmentCreate,
    request: Request,
    principal: SellerOrAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> ShipmentResponse:
    shipment = await service.create_shipment(
        data, principal, idempotency_key, _request_id(request)
    )
    return ShipmentResponse.model_validate(shipment)


@router.get("/by-order/{order_id}", response_model=ShipmentResponse)
async def get_shipment_by_order(
    order_id: UUID,
    principal: SellerOrAdmin,
    service: Service,
) -> ShipmentResponse:
    shipment = await service.get_by_order(order_id, principal)
    return ShipmentResponse.model_validate(shipment)


@router.get("/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: UUID,
    principal: SellerOrAdmin,
    service: Service,
) -> ShipmentResponse:
    shipment = await service.get_shipment(shipment_id, principal)
    return ShipmentResponse.model_validate(shipment)


@router.post("/{shipment_id}/ship", response_model=ShipmentResponse)
async def ship_shipment(
    shipment_id: UUID,
    data: ShipmentShip,
    request: Request,
    principal: SellerOrAdmin,
    service: Service,
) -> ShipmentResponse:
    shipment = await service.ship(shipment_id, data, principal, _request_id(request))
    return ShipmentResponse.model_validate(shipment)


@router.post("/{shipment_id}/deliver", response_model=ShipmentResponse)
async def deliver_shipment(
    shipment_id: UUID,
    data: ShipmentDeliver,
    request: Request,
    principal: SellerOrAdmin,
    service: Service,
) -> ShipmentResponse:
    shipment = await service.deliver(shipment_id, data, principal, _request_id(request))
    return ShipmentResponse.model_validate(shipment)


@router.post("/{shipment_id}/exception", response_model=ShipmentResponse)
async def report_shipment_exception(
    shipment_id: UUID,
    data: ShipmentException,
    request: Request,
    principal: SellerOrAdmin,
    service: Service,
) -> ShipmentResponse:
    shipment = await service.record_exception(
        shipment_id, data, principal, _request_id(request)
    )
    return ShipmentResponse.model_validate(shipment)
