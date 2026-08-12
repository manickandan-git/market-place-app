from uuid import uuid4

import pytest
from sqlalchemy import select

from app.dependencies.auth import Principal
from app.exceptions import ServiceError
from app.models.inventory import (
    InventoryItem,
    InventoryReservation,
    MovementReason,
    ReservationStatus,
)
from app.schemas.inventory import BatchReservationCreate, BatchReservationLine
from app.services.inventory_service import InventoryService


def principal(*, subject=None, roles=(), scopes=()) -> Principal:
    return Principal(
        subject=subject or uuid4(),
        roles=frozenset(roles),
        scopes=frozenset(scopes),
        claims={},
    )


async def make_item(
    session,
    *,
    seller_id,
    sku="SKU-1",
    on_hand=20,
    reserved=0,
) -> InventoryItem:
    item = InventoryItem(
        warehouse_id=uuid4(),
        product_id=uuid4(),
        variant_id=uuid4(),
        seller_id=seller_id,
        sku=sku,
        on_hand_quantity=on_hand,
        reserved_quantity=reserved,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


def batch(seller_id, sku, quantity, *, customer_id, **kwargs) -> BatchReservationCreate:
    return BatchReservationCreate(
        customer_id=customer_id,
        lines=[BatchReservationLine(sku=sku, seller_id=seller_id, quantity=quantity)],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# create_batch_reservation
# ---------------------------------------------------------------------------


async def test_batch_reservation_reserves_and_shares_group_id(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    item = await make_item(session, seller_id=seller, on_hand=20)
    buyer = principal(roles=["buyer"])

    group_id, reservations = await service.create_batch_reservation(
        batch(seller, "SKU-1", 5, customer_id=buyer.subject), buyer, None, None
    )

    assert len(reservations) == 1
    assert reservations[0].reservation_group_id == group_id
    assert reservations[0].quantity == 5
    assert reservations[0].status == ReservationStatus.ACTIVE

    await session.refresh(item)
    assert item.reserved_quantity == 5
    assert item.available_quantity == 15


async def test_batch_reservation_uses_customer_id_from_body_not_caller(session) -> None:
    """Regression test: the caller is now always a scoped service (or
    admin), never the buyer directly, so the reservation's owner must come
    from data.customer_id -- not principal.subject, which is the calling
    service's own fixed identity."""
    service = InventoryService(session)
    seller = uuid4()
    await make_item(session, seller_id=seller, sku="SKU-1B", on_hand=20)
    buyer_id = uuid4()
    order_service = principal(roles=["service"], scopes=["inventory:checkout"])
    assert order_service.subject != buyer_id

    _, reservations = await service.create_batch_reservation(
        batch(seller, "SKU-1B", 5, customer_id=buyer_id), order_service, None, None
    )

    assert reservations[0].customer_id == buyer_id
    assert reservations[0].customer_id != order_service.subject


async def test_batch_reservation_splits_across_warehouses(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    small = await make_item(session, seller_id=seller, sku="SKU-2", on_hand=3)
    large = await make_item(session, seller_id=seller, sku="SKU-2", on_hand=5)
    buyer = principal(roles=["buyer"])

    group_id, reservations = await service.create_batch_reservation(
        batch(seller, "SKU-2", 6, customer_id=buyer.subject), buyer, None, None
    )

    assert len(reservations) == 2
    assert {r.inventory_item_id for r in reservations} == {small.id, large.id}
    assert sum(r.quantity for r in reservations) == 6
    assert all(r.reservation_group_id == group_id for r in reservations)

    await session.refresh(small)
    await session.refresh(large)
    assert small.available_quantity + large.available_quantity == 2


async def test_batch_reservation_rejects_insufficient_stock(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    item = await make_item(session, seller_id=seller, sku="SKU-3", on_hand=4)
    buyer = principal(roles=["buyer"])

    with pytest.raises(ServiceError) as error:
        await service.create_batch_reservation(
            batch(seller, "SKU-3", 5, customer_id=buyer.subject), buyer, None, None
        )
    assert error.value.code == "insufficient_stock"

    await session.rollback()
    await session.refresh(item)
    assert item.reserved_quantity == 0
    reservations = (
        await session.scalars(
            select(InventoryReservation).where(
                InventoryReservation.inventory_item_id == item.id
            )
        )
    ).all()
    assert list(reservations) == []


async def test_batch_reservation_rejects_unknown_sku(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    buyer = principal(roles=["buyer"])

    with pytest.raises(ServiceError) as error:
        await service.create_batch_reservation(
            batch(seller, "NO-SUCH-SKU", 1, customer_id=buyer.subject), buyer, None, None
        )
    assert error.value.code == "invalid_sku"


async def test_batch_reservation_ignores_another_sellers_stock(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    other_seller = uuid4()
    await make_item(session, seller_id=other_seller, sku="SKU-4", on_hand=20)
    buyer = principal(roles=["buyer"])

    with pytest.raises(ServiceError) as error:
        await service.create_batch_reservation(
            batch(seller, "SKU-4", 1, customer_id=buyer.subject), buyer, None, None
        )
    assert error.value.code == "invalid_sku"


async def test_batch_reservation_is_idempotent(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    item = await make_item(session, seller_id=seller, sku="SKU-5", on_hand=20)
    buyer = principal(roles=["buyer"])
    data = batch(seller, "SKU-5", 5, customer_id=buyer.subject)

    group_id, reservations = await service.create_batch_reservation(
        data, buyer, None, "batch-key-1"
    )
    replay_group_id, replay_reservations = await service.create_batch_reservation(
        data, buyer, None, "batch-key-1"
    )

    assert replay_group_id == group_id
    assert [r.id for r in replay_reservations] == [r.id for r in reservations]
    await session.refresh(item)
    assert item.reserved_quantity == 5


async def test_batch_reservation_idempotency_is_scoped_per_customer(session) -> None:
    """Regression test: idempotency used to be keyed by principal.subject,
    which was safely per-buyer when the buyer's own JWT was forwarded. Now
    every checkout call shares one calling-service principal, so the
    idempotency actor must be data.customer_id instead -- otherwise two
    different buyers reusing the same client-supplied Idempotency-Key
    would collide."""
    service = InventoryService(session)
    seller = uuid4()
    await make_item(session, seller_id=seller, sku="SKU-5B", on_hand=20)
    order_service = principal(roles=["service"], scopes=["inventory:checkout"])
    buyer_a = uuid4()
    buyer_b = uuid4()

    group_a, _ = await service.create_batch_reservation(
        batch(seller, "SKU-5B", 1, customer_id=buyer_a),
        order_service,
        None,
        "shared-key",
    )
    group_b, _ = await service.create_batch_reservation(
        batch(seller, "SKU-5B", 1, customer_id=buyer_b),
        order_service,
        None,
        "shared-key",
    )

    assert group_a != group_b


# ---------------------------------------------------------------------------
# commit_reservation_group
# ---------------------------------------------------------------------------


async def test_commit_reservation_group_persists_committed_status(session) -> None:
    """Regression test: _snapshot() must not silently discard the pending
    status=COMMITTED write by refreshing the object before it is flushed."""
    service = InventoryService(session)
    seller = uuid4()
    item = await make_item(session, seller_id=seller, sku="SKU-6", on_hand=20)
    buyer = principal(roles=["buyer"])
    group_id, _ = await service.create_batch_reservation(
        batch(seller, "SKU-6", 5, customer_id=buyer.subject), buyer, None, None
    )

    reservations = await service.commit_reservation_group(group_id, buyer, None)

    assert all(r.status == ReservationStatus.COMMITTED for r in reservations)
    await session.refresh(item)
    assert item.on_hand_quantity == 15
    assert item.reserved_quantity == 0

    # Re-read via a fresh query, independent of any in-memory session state,
    # to prove the COMMITTED status actually made it to the database.
    persisted = await session.scalar(
        select(InventoryReservation).where(
            InventoryReservation.reservation_group_id == group_id
        )
    )
    assert persisted.status == ReservationStatus.COMMITTED


async def test_commit_reservation_group_is_idempotent(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    item = await make_item(session, seller_id=seller, sku="SKU-7", on_hand=20)
    buyer = principal(roles=["buyer"])
    group_id, _ = await service.create_batch_reservation(
        batch(seller, "SKU-7", 5, customer_id=buyer.subject), buyer, None, None
    )

    await service.commit_reservation_group(group_id, buyer, None)
    second = await service.commit_reservation_group(group_id, buyer, None)

    assert all(r.status == ReservationStatus.COMMITTED for r in second)
    await session.refresh(item)
    assert item.on_hand_quantity == 15
    assert item.reserved_quantity == 0


async def test_commit_reservation_group_rejects_mixed_status(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    await make_item(session, seller_id=seller, sku="SKU-8", on_hand=20)
    buyer = principal(roles=["buyer"])
    group_id, reservations = await service.create_batch_reservation(
        batch(seller, "SKU-8", 5, customer_id=buyer.subject), buyer, None, None
    )

    reservations[0].status = ReservationStatus.RELEASED
    await session.commit()

    with pytest.raises(ServiceError) as error:
        await service.commit_reservation_group(group_id, buyer, None)
    assert error.value.code == "reservation_group_not_active"


async def test_commit_reservation_group_not_found(session) -> None:
    service = InventoryService(session)
    buyer = principal(roles=["buyer"])

    with pytest.raises(ServiceError) as error:
        await service.commit_reservation_group(uuid4(), buyer, None)
    assert error.value.code == "reservation_group_not_found"


async def test_commit_reservation_group_rejects_other_customer(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    await make_item(session, seller_id=seller, sku="SKU-9", on_hand=20)
    buyer = principal(roles=["buyer"])
    group_id, _ = await service.create_batch_reservation(
        batch(seller, "SKU-9", 5, customer_id=buyer.subject), buyer, None, None
    )

    stranger = principal(roles=["buyer"])
    with pytest.raises(ServiceError) as error:
        await service.commit_reservation_group(group_id, stranger, None)
    assert error.value.code == "reservation_forbidden"


# ---------------------------------------------------------------------------
# release_reservation_group
# ---------------------------------------------------------------------------


async def test_release_reservation_group_restores_availability(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    item = await make_item(session, seller_id=seller, sku="SKU-10", on_hand=20)
    buyer = principal(roles=["buyer"])
    group_id, _ = await service.create_batch_reservation(
        batch(seller, "SKU-10", 5, customer_id=buyer.subject), buyer, None, None
    )

    reservations = await service.release_reservation_group(
        group_id, MovementReason.CUSTOMER_CANCELLED, None, buyer, None
    )

    assert all(r.status == ReservationStatus.RELEASED for r in reservations)
    await session.refresh(item)
    assert item.on_hand_quantity == 20
    assert item.reserved_quantity == 0
    assert item.available_quantity == 20


async def test_release_reservation_group_is_idempotent(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    item = await make_item(session, seller_id=seller, sku="SKU-11", on_hand=20)
    buyer = principal(roles=["buyer"])
    group_id, _ = await service.create_batch_reservation(
        batch(seller, "SKU-11", 5, customer_id=buyer.subject), buyer, None, None
    )

    await service.release_reservation_group(
        group_id, MovementReason.CUSTOMER_CANCELLED, None, buyer, None
    )
    second = await service.release_reservation_group(
        group_id, MovementReason.CUSTOMER_CANCELLED, None, buyer, None
    )

    assert all(r.status == ReservationStatus.RELEASED for r in second)
    await session.refresh(item)
    assert item.available_quantity == 20


async def test_release_reservation_group_rejects_committed_group(session) -> None:
    service = InventoryService(session)
    seller = uuid4()
    await make_item(session, seller_id=seller, sku="SKU-12", on_hand=20)
    buyer = principal(roles=["buyer"])
    group_id, _ = await service.create_batch_reservation(
        batch(seller, "SKU-12", 5, customer_id=buyer.subject), buyer, None, None
    )
    await service.commit_reservation_group(group_id, buyer, None)

    with pytest.raises(ServiceError) as error:
        await service.release_reservation_group(
            group_id, MovementReason.CUSTOMER_CANCELLED, None, buyer, None
        )
    assert error.value.code == "reservation_group_not_active"
