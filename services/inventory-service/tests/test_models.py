from uuid import uuid4

from app.models.inventory import InventoryItem, ReservationStatus


def test_available_quantity_is_derived() -> None:
    item = InventoryItem(
        warehouse_id=uuid4(),
        product_id=uuid4(),
        variant_id=uuid4(),
        seller_id=uuid4(),
        sku="SKU-1",
        on_hand_quantity=12,
        reserved_quantity=5,
        low_stock_threshold=2,
    )
    assert item.available_quantity == 7


def test_reservation_status_values_are_stable() -> None:
    assert ReservationStatus.ACTIVE.value == "active"
    assert ReservationStatus.COMMITTED.value == "committed"
    assert ReservationStatus.RELEASED.value == "released"
    assert ReservationStatus.EXPIRED.value == "expired"


def test_inventory_table_has_safety_constraints() -> None:
    names = {
        constraint.name
        for constraint in InventoryItem.__table__.constraints
        if constraint.name
    }
    assert "ck_inventory_items_reserved_not_above_on_hand" in names
    assert "ck_inventory_items_on_hand_non_negative" in names
