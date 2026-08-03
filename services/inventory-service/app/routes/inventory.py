from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.dependencies.auth import (
    Principal,
    get_current_principal,
    require_roles,
    require_scope,
)
from app.dependencies.headers import optional_idempotency_key, required_version
from app.models.inventory import ReservationStatus
from app.routes.dependencies import get_inventory_service
from app.schemas.common import PaginatedResponse
from app.schemas.inventory import (
    AvailabilityResponse,
    BatchReservationCreate,
    CatalogSkuResponse,
    CatalogSkuSync,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    MovementResponse,
    ReservationCommit,
    ReservationCreate,
    ReservationGroupResponse,
    ReservationRelease,
    ReservationResponse,
    StockAdjustment,
    WarehouseCreate,
    WarehouseResponse,
    WarehouseUpdate,
)
from app.services.inventory_service import InventoryService

router = APIRouter()
AuthenticatedPrincipal = Annotated[Principal, Depends(get_current_principal)]
SellerPrincipal = Annotated[Principal, Depends(require_roles("seller", "admin"))]
AdminPrincipal = Annotated[Principal, Depends(require_roles("admin"))]
ExpiryPrincipal = Annotated[Principal, Depends(require_scope("inventory:expire"))]
SyncPrincipal = Annotated[Principal, Depends(require_scope("inventory:sync"))]
Service = Annotated[InventoryService, Depends(get_inventory_service)]
Version = Annotated[int, Depends(required_version)]
IdempotencyKey = Annotated[str | None, Depends(optional_idempotency_key)]


@router.get(
    "/availability/{sku}",
    response_model=AvailabilityResponse,
    tags=["availability"],
)
async def get_availability(
    sku: str,
    service: Service,
    quantity: int = Query(default=1, ge=1, le=1_000_000),
) -> AvailabilityResponse:
    normalized_sku = sku.strip().upper()
    available = await service.repo.get_availability(normalized_sku)
    return AvailabilityResponse(
        sku=normalized_sku,
        available_quantity=available,
        is_available=available >= quantity,
    )


@router.put(
    "/internal/catalog-skus/{variant_id}",
    response_model=CatalogSkuResponse,
    tags=["integration"],
)
async def sync_catalog_sku(
    variant_id: UUID,
    data: CatalogSkuSync,
    request: Request,
    principal: SyncPrincipal,
    service: Service,
):
    if variant_id != data.variant_id:
        from app.exceptions import ServiceError

        raise ServiceError(
            422,
            "variant_id_mismatch",
            "Route and payload variant IDs must match",
        )
    return await service.sync_catalog_sku(
        data,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/admin/warehouses",
    response_model=list[WarehouseResponse],
    tags=["warehouses"],
)
async def list_warehouses(
    _principal: AdminPrincipal,
    service: Service,
    active_only: bool = True,
):
    return await service.repo.list_warehouses(active_only=active_only)


@router.post(
    "/admin/warehouses",
    response_model=WarehouseResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["warehouses"],
)
async def create_warehouse(
    data: WarehouseCreate,
    request: Request,
    principal: AdminPrincipal,
    service: Service,
):
    return await service.create_warehouse(
        data,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.patch(
    "/admin/warehouses/{warehouse_id}",
    response_model=WarehouseResponse,
    tags=["warehouses"],
)
async def update_warehouse(
    warehouse_id: UUID,
    data: WarehouseUpdate,
    request: Request,
    principal: AdminPrincipal,
    service: Service,
    expected_version: Version,
):
    return await service.update_warehouse(
        warehouse_id,
        data,
        expected_version,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/seller/inventory",
    response_model=PaginatedResponse[InventoryItemResponse],
    tags=["seller inventory"],
)
async def list_inventory(
    principal: SellerPrincipal,
    service: Service,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    warehouse_id: UUID | None = None,
    sku: str | None = Query(default=None, min_length=2, max_length=80),
    low_stock_only: bool = False,
):
    items, total = await service.repo.list_items(
        page=page,
        page_size=page_size,
        seller_id=None if principal.has_role("admin") else principal.subject,
        warehouse_id=warehouse_id,
        sku=sku.strip().upper() if sku else None,
        low_stock_only=low_stock_only,
    )
    responses = [InventoryItemResponse.from_item(item) for item in items]
    return PaginatedResponse[InventoryItemResponse].create(
        items=responses,
        page=page,
        page_size=page_size,
        total_items=total,
    )


@router.post(
    "/seller/inventory",
    response_model=InventoryItemResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["seller inventory"],
)
async def create_inventory_item(
    data: InventoryItemCreate,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> InventoryItemResponse:
    item = await service.create_item(
        data,
        principal,
        getattr(request.state, "request_id", None),
        idempotency_key,
    )
    return InventoryItemResponse.from_item(item)


@router.get(
    "/seller/inventory/{item_id}",
    response_model=InventoryItemResponse,
    tags=["seller inventory"],
)
async def get_inventory_item(
    item_id: UUID,
    principal: SellerPrincipal,
    service: Service,
) -> InventoryItemResponse:
    item = await service._managed_item(item_id, principal)
    return InventoryItemResponse.from_item(item)


@router.patch(
    "/seller/inventory/{item_id}",
    response_model=InventoryItemResponse,
    tags=["seller inventory"],
)
async def update_inventory_item(
    item_id: UUID,
    data: InventoryItemUpdate,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
    expected_version: Version,
) -> InventoryItemResponse:
    item = await service.update_item(
        item_id,
        data,
        expected_version,
        principal,
        getattr(request.state, "request_id", None),
    )
    return InventoryItemResponse.from_item(item)


@router.post(
    "/seller/inventory/{item_id}/adjustments",
    response_model=InventoryItemResponse,
    tags=["stock"],
)
async def adjust_stock(
    item_id: UUID,
    data: StockAdjustment,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
    expected_version: Version,
    idempotency_key: IdempotencyKey,
) -> InventoryItemResponse:
    item = await service.adjust_stock(
        item_id,
        data,
        expected_version,
        principal,
        getattr(request.state, "request_id", None),
        idempotency_key,
    )
    return InventoryItemResponse.from_item(item)


@router.get(
    "/seller/inventory/{item_id}/movements",
    response_model=PaginatedResponse[MovementResponse],
    tags=["stock"],
)
async def list_movements(
    item_id: UUID,
    principal: SellerPrincipal,
    service: Service,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    await service._managed_item(item_id, principal)
    items, total = await service.repo.list_movements(
        item_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[MovementResponse].create(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total,
    )


@router.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["reservations"],
)
async def create_reservation(
    data: ReservationCreate,
    request: Request,
    principal: AuthenticatedPrincipal,
    service: Service,
    idempotency_key: IdempotencyKey,
):
    return await service.create_reservation(
        data,
        principal,
        getattr(request.state, "request_id", None),
        idempotency_key,
    )


@router.get(
    "/reservations",
    response_model=PaginatedResponse[ReservationResponse],
    tags=["reservations"],
)
async def list_my_reservations(
    principal: AuthenticatedPrincipal,
    service: Service,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    reservation_status: ReservationStatus | None = Query(
        default=None,
        alias="status",
    ),
):
    items, total = await service.repo.list_reservations(
        customer_id=None if principal.has_role("admin") else principal.subject,
        status=reservation_status,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[ReservationResponse].create(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total,
    )


@router.post(
    "/reservations/{reservation_id}/commit",
    response_model=ReservationResponse,
    tags=["reservations"],
)
async def commit_reservation(
    reservation_id: UUID,
    data: ReservationCommit,
    request: Request,
    principal: AuthenticatedPrincipal,
    service: Service,
):
    return await service.commit_reservation(
        reservation_id,
        data.order_reference,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.post(
    "/reservations/{reservation_id}/release",
    response_model=ReservationResponse,
    tags=["reservations"],
)
async def release_reservation(
    reservation_id: UUID,
    data: ReservationRelease,
    request: Request,
    principal: AuthenticatedPrincipal,
    service: Service,
):
    return await service.release_reservation(
        reservation_id,
        data.reason,
        data.note,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.post(
    "/internal/checkout/reservations/batch",
    response_model=ReservationGroupResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["checkout"],
)
async def create_reservation_batch(
    data: BatchReservationCreate,
    request: Request,
    principal: AuthenticatedPrincipal,
    service: Service,
    idempotency_key: IdempotencyKey,
):
    group_id, reservations = await service.create_batch_reservation(
        data,
        principal,
        getattr(request.state, "request_id", None),
        idempotency_key,
    )
    return ReservationGroupResponse.from_reservations(group_id, reservations)


@router.post(
    "/internal/checkout/reservations/{group_id}/commit",
    response_model=ReservationGroupResponse,
    tags=["checkout"],
)
async def commit_reservation_batch(
    group_id: UUID,
    request: Request,
    principal: AuthenticatedPrincipal,
    service: Service,
):
    reservations = await service.commit_reservation_group(
        group_id,
        principal,
        getattr(request.state, "request_id", None),
    )
    return ReservationGroupResponse.from_reservations(group_id, reservations)


@router.post(
    "/internal/checkout/reservations/{group_id}/release",
    response_model=ReservationGroupResponse,
    tags=["checkout"],
)
async def release_reservation_batch(
    group_id: UUID,
    data: ReservationRelease,
    request: Request,
    principal: AuthenticatedPrincipal,
    service: Service,
):
    reservations = await service.release_reservation_group(
        group_id,
        data.reason,
        data.note,
        principal,
        getattr(request.state, "request_id", None),
    )
    return ReservationGroupResponse.from_reservations(group_id, reservations)


@router.post("/internal/reservations/expire", tags=["reservations"])
async def expire_reservations(
    request: Request,
    principal: ExpiryPrincipal,
    service: Service,
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, int]:
    count = await service.expire_reservations(
        principal,
        getattr(request.state, "request_id", None),
        limit,
    )
    return {"expired_count": count}
