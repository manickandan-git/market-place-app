from uuid import uuid4

import pytest

from app.config import Settings
from app.dependencies.auth import Principal
from app.exceptions import ServiceError
from app.models.shipment import ShipmentStatus
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentDeliver,
    ShipmentException,
    ShipmentShip,
)
from app.services.shipment_service import ShipmentService


class FakeOrderClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.fail_status: str | None = None
        self.fail_error: ServiceError | None = None

    async def advance_fulfillment(
        self,
        order_id,
        status,
        shipment_reference,
        occurred_at,
        service_token,
        request_id,
    ):
        if self.fail_status == status:
            raise self.fail_error or ServiceError(
                409, "invalid_order_transition", "Order is not in a valid state"
            )
        self.calls.append(
            {
                "order_id": order_id,
                "status": status,
                "shipment_reference": shipment_reference,
                "occurred_at": occurred_at,
            }
        )


class FakeAuthClient:
    async def service_token(self):
        return "fake-service-token"


def principal(*, subject=None, roles=("seller",)) -> Principal:
    return Principal(
        subject=subject or uuid4(),
        roles=frozenset(roles),
        scopes=frozenset(),
        claims={},
    )


def build_service(session, order_client=None):
    order_client = order_client or FakeOrderClient()
    service = ShipmentService(session, Settings(), order_client, FakeAuthClient())
    return service, order_client


# ---------------------------------------------------------------------------
# create_shipment
# ---------------------------------------------------------------------------


async def test_create_shipment_calls_order_processing(session) -> None:
    service, orders = build_service(session)
    seller = principal()
    order_id = uuid4()

    shipment = await service.create_shipment(
        ShipmentCreate(order_id=order_id, carrier="UPS"),
        seller,
        "create-key-1",
        None,
    )

    assert shipment.status == ShipmentStatus.PENDING
    assert shipment.seller_id == seller.subject
    assert len(orders.calls) == 1
    assert orders.calls[0] == {
        "order_id": order_id,
        "status": "processing",
        "shipment_reference": None,
        "occurred_at": None,
    }


async def test_create_shipment_is_idempotent(session) -> None:
    service, orders = build_service(session)
    seller = principal()
    data = ShipmentCreate(order_id=uuid4(), carrier="UPS")

    first = await service.create_shipment(data, seller, "same-key", None)
    replay = await service.create_shipment(data, seller, "same-key", None)

    assert replay.id == first.id
    assert len(orders.calls) == 1


async def test_create_shipment_rejects_duplicate_for_order(session) -> None:
    service, _ = build_service(session)
    seller = principal()
    order_id = uuid4()
    await service.create_shipment(
        ShipmentCreate(order_id=order_id, carrier="UPS"), seller, "key-a", None
    )

    with pytest.raises(ServiceError) as exc:
        await service.create_shipment(
            ShipmentCreate(order_id=order_id, carrier="FedEx"), seller, "key-b", None
        )
    assert exc.value.code == "shipment_already_exists"


async def test_create_shipment_propagates_order_rejection_and_creates_nothing(
    session,
) -> None:
    orders = FakeOrderClient()
    orders.fail_status = "processing"
    service, _ = build_service(session, order_client=orders)
    seller = principal()
    order_id = uuid4()

    with pytest.raises(ServiceError) as exc:
        await service.create_shipment(
            ShipmentCreate(order_id=order_id, carrier="UPS"), seller, "key-c", None
        )
    assert exc.value.code == "invalid_order_transition"
    assert await service.repo.get_by_order(order_id) is None


# ---------------------------------------------------------------------------
# ship / deliver / exception
# ---------------------------------------------------------------------------


async def test_ship_transitions_to_shipped_and_calls_order(session) -> None:
    service, orders = build_service(session)
    seller = principal()
    shipment = await service.create_shipment(
        ShipmentCreate(order_id=uuid4(), carrier="UPS"), seller, "ship-key-1", None
    )

    shipped = await service.ship(
        shipment.id, ShipmentShip(tracking_number="1Z999"), seller, None
    )

    assert shipped.status == ShipmentStatus.SHIPPED
    assert shipped.tracking_number == "1Z999"
    assert shipped.shipped_at is not None
    assert orders.calls[-1]["status"] == "shipped"
    assert orders.calls[-1]["shipment_reference"] == "1Z999"


async def test_ship_rejects_already_shipped(session) -> None:
    service, _ = build_service(session)
    seller = principal()
    shipment = await service.create_shipment(
        ShipmentCreate(order_id=uuid4(), carrier="UPS"), seller, "ship-key-2", None
    )
    await service.ship(shipment.id, ShipmentShip(tracking_number="1Z1"), seller, None)

    with pytest.raises(ServiceError) as exc:
        await service.ship(
            shipment.id, ShipmentShip(tracking_number="1Z2"), seller, None
        )
    assert exc.value.code == "shipment_not_pending"


async def test_deliver_transitions_to_delivered(session) -> None:
    service, orders = build_service(session)
    seller = principal()
    shipment = await service.create_shipment(
        ShipmentCreate(order_id=uuid4(), carrier="UPS"), seller, "deliver-key-1", None
    )
    await service.ship(shipment.id, ShipmentShip(tracking_number="1Z1"), seller, None)

    delivered = await service.deliver(shipment.id, ShipmentDeliver(), seller, None)

    assert delivered.status == ShipmentStatus.DELIVERED
    assert delivered.delivered_at is not None
    assert orders.calls[-1]["status"] == "delivered"


async def test_deliver_rejects_before_shipped(session) -> None:
    service, _ = build_service(session)
    seller = principal()
    shipment = await service.create_shipment(
        ShipmentCreate(order_id=uuid4(), carrier="UPS"), seller, "deliver-key-2", None
    )

    with pytest.raises(ServiceError) as exc:
        await service.deliver(shipment.id, ShipmentDeliver(), seller, None)
    assert exc.value.code == "shipment_not_shipped"


async def test_record_exception_marks_failed_without_order_call(session) -> None:
    service, orders = build_service(session)
    seller = principal()
    shipment = await service.create_shipment(
        ShipmentCreate(order_id=uuid4(), carrier="UPS"), seller, "exc-key-1", None
    )
    calls_before = len(orders.calls)

    failed = await service.record_exception(
        shipment.id, ShipmentException(reason="Lost in transit"), seller, None
    )

    assert failed.status == ShipmentStatus.FAILED
    assert failed.failure_reason == "Lost in transit"
    assert len(orders.calls) == calls_before


async def test_record_exception_rejects_terminal_shipment(session) -> None:
    service, _ = build_service(session)
    seller = principal()
    shipment = await service.create_shipment(
        ShipmentCreate(order_id=uuid4(), carrier="UPS"), seller, "exc-key-2", None
    )
    await service.ship(shipment.id, ShipmentShip(tracking_number="1Z1"), seller, None)
    await service.deliver(shipment.id, ShipmentDeliver(), seller, None)

    with pytest.raises(ServiceError) as exc:
        await service.record_exception(
            shipment.id, ShipmentException(reason="too late"), seller, None
        )
    assert exc.value.code == "shipment_not_active"


# ---------------------------------------------------------------------------
# reads / ownership
# ---------------------------------------------------------------------------


async def test_get_shipment_hides_other_sellers_shipment(session) -> None:
    service, _ = build_service(session)
    seller = principal()
    shipment = await service.create_shipment(
        ShipmentCreate(order_id=uuid4(), carrier="UPS"), seller, "own-key-1", None
    )

    stranger = principal()
    with pytest.raises(ServiceError) as exc:
        await service.get_shipment(shipment.id, stranger)
    assert exc.value.code == "shipment_not_found"

    fetched = await service.get_shipment(shipment.id, seller)
    assert fetched.id == shipment.id

    admin = principal(roles=("admin",))
    assert (await service.get_shipment(shipment.id, admin)).id == shipment.id


async def test_get_by_order_returns_owned_shipment(session) -> None:
    service, _ = build_service(session)
    seller = principal()
    order_id = uuid4()
    created = await service.create_shipment(
        ShipmentCreate(order_id=order_id, carrier="UPS"), seller, "order-key-1", None
    )

    found = await service.get_by_order(order_id, seller)
    assert found.id == created.id
