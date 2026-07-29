from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.inventory import MovementReason
from app.schemas.inventory import (
    CatalogSkuSync,
    InventoryItemCreate,
    InventoryItemUpdate,
    ReservationCreate,
    StockAdjustment,
    WarehouseCreate,
    WarehouseUpdate,
)


def test_warehouse_code_is_normalized() -> None:
    value = WarehouseCreate(code="atl_01", name="Atlanta").code
    assert value == "ATL_01"


def test_sku_is_normalized() -> None:
    data = InventoryItemCreate(
        warehouse_id=uuid4(),
        product_id=uuid4(),
        variant_id=uuid4(),
        sku="demo-sku.1",
    )
    assert data.sku == "DEMO-SKU.1"


def test_catalog_sku_is_normalized() -> None:
    data = CatalogSkuSync(
        product_id=uuid4(),
        variant_id=uuid4(),
        seller_id=uuid4(),
        sku="widget-blue",
        is_active=True,
    )
    assert data.sku == "WIDGET-BLUE"


def test_stock_adjustment_rejects_zero() -> None:
    with pytest.raises(ValidationError):
        StockAdjustment(
            quantity_delta=0,
            reason=MovementReason.CYCLE_COUNT,
        )


def test_stock_adjustment_accepts_negative() -> None:
    data = StockAdjustment(
        quantity_delta=-3,
        reason=MovementReason.DAMAGE,
    )
    assert data.quantity_delta == -3


def test_reservation_requires_positive_quantity() -> None:
    with pytest.raises(ValidationError):
        ReservationCreate(inventory_item_id=uuid4(), quantity=0)


def test_reservation_accepts_aware_expiry() -> None:
    data = ReservationCreate(
        inventory_item_id=uuid4(),
        quantity=2,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    assert data.quantity == 2


def test_empty_inventory_patch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InventoryItemUpdate()


def test_empty_warehouse_patch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WarehouseUpdate()
