from uuid import uuid4

import pytest

from app.dependencies.auth import Principal
from app.exceptions import ServiceError
from app.models.inventory import InventoryItem
from app.services.inventory_service import InventoryService


def principal(role: str = "seller") -> Principal:
    return Principal(
        subject=uuid4(),
        roles=frozenset({role}),
        scopes=frozenset(),
        claims={},
    )


def item(owner_id):
    return InventoryItem(
        warehouse_id=uuid4(),
        product_id=uuid4(),
        variant_id=uuid4(),
        seller_id=owner_id,
        sku="SKU-1",
        on_hand_quantity=10,
        reserved_quantity=2,
        low_stock_threshold=2,
        version=3,
    )


def test_seller_can_manage_owned_inventory() -> None:
    owner = principal()
    assert InventoryService._can_manage(item(owner.subject), owner)


def test_seller_cannot_manage_another_sellers_inventory() -> None:
    owner = principal()
    other = principal()
    assert not InventoryService._can_manage(item(owner.subject), other)


def test_admin_can_manage_any_inventory() -> None:
    owner = principal()
    admin = principal("admin")
    assert InventoryService._can_manage(item(owner.subject), admin)


def test_version_conflict_is_detected() -> None:
    resource = item(uuid4())
    with pytest.raises(ServiceError) as error:
        InventoryService._check_version(resource, 2)
    assert error.value.status_code == 412


def test_matching_version_is_accepted() -> None:
    resource = item(uuid4())
    InventoryService._check_version(resource, 3)


def test_no_version_is_accepted() -> None:
    resource = item(uuid4())
    InventoryService._check_version(resource, None)
    