from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.auth import Principal
from app.config import Settings
from app.exceptions import ServiceError
from app.models import OrderStatus, PaymentStatus
from app.schemas import (
    AddressSnapshot,
    BatchReservationResponse,
    CancelOrder,
    CartItemSnapshot,
    CartSnapshot,
    FulfillmentUpdate,
    OrderCreate,
    PaymentAuthorized,
    PaymentFailed,
    PaymentRefunded,
)
from app.service import OrderService


class FakeCart:
    def __init__(self, cart: CartSnapshot):
        self.cart = cart
        self.checked_out = False
        self.checked_out_token: str | None = None

    async def snapshot(self, *_args):
        return self.cart

    async def mark_checked_out(self, cart_id, order_id, token, request_id):
        self.checked_out = True
        self.checked_out_token = token


class FakeProducts:
    def __init__(self, seller_id):
        self.seller_id = seller_id

    async def seller_for_product(self, *_args):
        return self.seller_id


class FakeInventory:
    def __init__(self):
        self.group_id = uuid4()
        self.reserved = self.committed = self.released = False

    async def reserve_batch(self, data, *_args):
        self.reserved = True
        assert data.lines[0].sku == "SKU-1"
        return BatchReservationResponse(
            reservation_group_id=self.group_id,
            reservation_ids=[uuid4()],
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    async def commit_group(self, *_args):
        self.committed = True

    async def release_group(self, *_args):
        self.released = True


class FakeNotifications:
    async def order_event(self, *_args):
        return None


@pytest.fixture
def customer_id():
    return uuid4()


@pytest.fixture
def principal(customer_id):
    return Principal(customer_id, frozenset({"buyer"}), frozenset(), {})


@pytest.fixture
def create_data():
    address = AddressSnapshot(
        full_name="Test Buyer",
        line1="1 Main St",
        city="Atlanta",
        state_or_region="GA",
        postal_code="30024",
        country_code="US",
    )
    return OrderCreate(cart_id=uuid4(), cart_version=1, shipping_address=address)


def build_service(session, customer_id, create_data):
    seller_id = uuid4()
    cart = CartSnapshot(
        id=create_data.cart_id,
        customer_id=customer_id,
        status="active",
        currency_code="USD",
        subtotal=Decimal("39.98"),
        version=1,
        items=[
            CartItemSnapshot(
                product_id=uuid4(),
                variant_id=uuid4(),
                sku="SKU-1",
                product_name="Product",
                variant_name="Default",
                quantity=2,
                unit_price=Decimal("19.99"),
                currency_code="USD",
                product_version=3,
            )
        ],
    )
    inventory = FakeInventory()
    carts = FakeCart(cart)
    service = OrderService(
        session,
        Settings(database_url="sqlite+aiosqlite:///:memory:"),
        carts,
        FakeProducts(seller_id),
        inventory,
        FakeNotifications(),
    )
    return service, carts, inventory


@pytest.mark.asyncio
async def test_create_order_reserves_inventory_and_is_idempotent(
    session, customer_id, principal, create_data
):
    service, carts, inventory = build_service(session, customer_id, create_data)
    order = await service.create(
        create_data, principal, "buyer-token", "checkout-key-123", "request-1"
    )
    replay = await service.create(
        create_data, principal, "buyer-token", "checkout-key-123", "request-2"
    )
    assert order.id == replay.id
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.grand_total == Decimal("39.98")
    assert len(order.items) == 1
    assert inventory.reserved
    assert carts.checked_out
    assert carts.checked_out_token == "buyer-token"


@pytest.mark.asyncio
async def test_second_checkout_of_same_cart_is_rejected(
    session, customer_id, principal, create_data
):
    service, _, inventory = build_service(session, customer_id, create_data)
    await service.create(create_data, principal, "token", "checkout-key-a", None)
    inventory.reserved = False

    with pytest.raises(ServiceError) as exc:
        await service.create(create_data, principal, "token", "checkout-key-b", None)
    assert exc.value.code == "order_already_exists"
    # Rejected by the upfront by_customer_cart check, before ever asking
    # Inventory to reserve stock a second time for the same cart.
    assert not inventory.reserved


@pytest.mark.asyncio
async def test_concurrent_duplicate_checkout_hits_db_constraint_not_500(
    session, customer_id, principal, create_data
):
    """Simulates the race the upfront by_customer_cart check can't close:
    a second request's read of by_customer_cart happens before the first
    request's transaction commits, so both proceed to insert. The DB's
    unique constraint is the real backstop; this pins that it surfaces as
    a clean 409, not an unhandled 500."""
    service, _, inventory = build_service(session, customer_id, create_data)
    await service.create(create_data, principal, "token", "checkout-key-e", None)
    inventory.reserved = False

    async def _stale_read(*_args):
        return None

    service.repo.by_customer_cart = _stale_read

    with pytest.raises(ServiceError) as exc:
        await service.create(create_data, principal, "token", "checkout-key-f", None)
    assert exc.value.code == "order_already_exists"
    assert inventory.released


@pytest.mark.asyncio
async def test_idempotency_key_rejects_different_payload(
    session, customer_id, principal, create_data
):
    service, _, _ = build_service(session, customer_id, create_data)
    await service.create(create_data, principal, "token", "same-key-123", None)
    changed = create_data.model_copy(update={"cart_version": 2})
    with pytest.raises(ServiceError) as exc:
        await service.create(changed, principal, "token", "same-key-123", None)
    assert exc.value.code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_payment_authorization_commits_inventory(
    session, customer_id, principal, create_data
):
    service, _, inventory = build_service(session, customer_id, create_data)
    order = await service.create(create_data, principal, "token", "pay-key-123", None)
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})
    updated = await service.payment_authorized(
        order.id,
        PaymentAuthorized(
            payment_reference="pay-1",
            authorized_amount=Decimal("39.98"),
            currency_code="USD",
        ),
        payment,
        "service-token",
        None,
    )
    assert updated.status == OrderStatus.CONFIRMED
    assert updated.payment_status == PaymentStatus.AUTHORIZED
    assert inventory.committed


@pytest.mark.asyncio
async def test_payment_failure_releases_inventory(
    session, customer_id, principal, create_data
):
    service, _, inventory = build_service(session, customer_id, create_data)
    order = await service.create(create_data, principal, "token", "fail-key-123", None)
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})
    updated = await service.payment_failed(
        order.id,
        PaymentFailed(reason="declined"),
        payment,
        "service-token",
        None,
    )
    assert updated.status == OrderStatus.PAYMENT_FAILED
    assert inventory.released


async def _authorized_order(service, customer_id, principal, create_data, key):
    order = await service.create(create_data, principal, "token", key, None)
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})
    return await service.payment_authorized(
        order.id,
        PaymentAuthorized(
            payment_reference="pay-1",
            authorized_amount=Decimal("39.98"),
            currency_code="USD",
        ),
        payment,
        "service-token",
        None,
    )


@pytest.mark.asyncio
async def test_full_refund_marks_order_refunded_without_changing_status(
    session, customer_id, principal, create_data
):
    service, _, _ = build_service(session, customer_id, create_data)
    order = await _authorized_order(
        service, customer_id, principal, create_data, "refund-key-1"
    )
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})

    refunded = await service.payment_refunded(
        order.id,
        PaymentRefunded(refunded_amount=Decimal("39.98"), currency_code="USD"),
        payment,
        None,
    )

    assert refunded.payment_status == PaymentStatus.REFUNDED
    assert refunded.status == OrderStatus.CONFIRMED


@pytest.mark.asyncio
async def test_partial_refund_marks_order_partially_refunded(
    session, customer_id, principal, create_data
):
    service, _, _ = build_service(session, customer_id, create_data)
    order = await _authorized_order(
        service, customer_id, principal, create_data, "refund-key-2"
    )
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})

    refunded = await service.payment_refunded(
        order.id,
        PaymentRefunded(refunded_amount=Decimal("10.00"), currency_code="USD"),
        payment,
        None,
    )

    assert refunded.payment_status == PaymentStatus.PARTIALLY_REFUNDED
    assert refunded.status == OrderStatus.CONFIRMED


@pytest.mark.asyncio
async def test_refund_replay_with_same_amount_is_idempotent(
    session, customer_id, principal, create_data
):
    service, _, _ = build_service(session, customer_id, create_data)
    order = await _authorized_order(
        service, customer_id, principal, create_data, "refund-key-3"
    )
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})
    data = PaymentRefunded(refunded_amount=Decimal("39.98"), currency_code="USD")

    first = await service.payment_refunded(order.id, data, payment, None)
    replay = await service.payment_refunded(order.id, data, payment, None)

    assert first.payment_status == replay.payment_status == PaymentStatus.REFUNDED


@pytest.mark.asyncio
async def test_refund_rejects_unpaid_order(
    session, customer_id, principal, create_data
):
    service, _, _ = build_service(session, customer_id, create_data)
    order = await service.create(create_data, principal, "token", "refund-key-4", None)
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})

    with pytest.raises(ServiceError) as exc:
        await service.payment_refunded(
            order.id,
            PaymentRefunded(refunded_amount=Decimal("10.00"), currency_code="USD"),
            payment,
            None,
        )
    assert exc.value.code == "invalid_order_state"


@pytest.mark.asyncio
async def test_refund_rejects_currency_mismatch(
    session, customer_id, principal, create_data
):
    service, _, _ = build_service(session, customer_id, create_data)
    order = await _authorized_order(
        service, customer_id, principal, create_data, "refund-key-5"
    )
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})

    with pytest.raises(ServiceError) as exc:
        await service.payment_refunded(
            order.id,
            PaymentRefunded(refunded_amount=Decimal("10.00"), currency_code="EUR"),
            payment,
            None,
        )
    assert exc.value.code == "payment_amount_mismatch"


@pytest.mark.asyncio
async def test_refund_rejects_amount_exceeding_grand_total(
    session, customer_id, principal, create_data
):
    service, _, _ = build_service(session, customer_id, create_data)
    order = await _authorized_order(
        service, customer_id, principal, create_data, "refund-key-6"
    )
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})

    with pytest.raises(ServiceError) as exc:
        await service.payment_refunded(
            order.id,
            PaymentRefunded(refunded_amount=Decimal("100.00"), currency_code="USD"),
            payment,
            None,
        )
    assert exc.value.code == "payment_amount_mismatch"


@pytest.mark.asyncio
async def test_customer_cancellation_checks_version(
    session, customer_id, principal, create_data
):
    service, _, inventory = build_service(session, customer_id, create_data)
    order = await service.create(create_data, principal, "token", "cancel-key-1", None)
    with pytest.raises(ServiceError) as exc:
        await service.cancel(
            order.id, CancelOrder(reason="Changed mind"), principal, "token", 99, None
        )
    assert exc.value.code == "version_conflict"
    cancelled = await service.cancel(
        order.id,
        CancelOrder(reason="Changed mind"),
        principal,
        "token",
        order.version,
        None,
    )
    assert cancelled.status == OrderStatus.CANCELLED
    assert inventory.released


@pytest.mark.asyncio
async def test_fulfillment_requires_ordered_transitions(
    session, customer_id, principal, create_data
):
    service, _, _ = build_service(session, customer_id, create_data)
    order = await service.create(create_data, principal, "token", "ship-key-12", None)
    payment = Principal(uuid4(), frozenset(), frozenset({"orders:payment"}), {})
    await service.payment_authorized(
        order.id,
        PaymentAuthorized(
            payment_reference="pay-2",
            authorized_amount=Decimal("39.98"),
            currency_code="USD",
        ),
        payment,
        "service-token",
        None,
    )
    fulfillment = Principal(uuid4(), frozenset(), frozenset({"orders:fulfillment"}), {})
    with pytest.raises(ServiceError):
        await service.fulfillment(
            order.id, FulfillmentUpdate(status=OrderStatus.SHIPPED), fulfillment, None
        )
    processing = await service.fulfillment(
        order.id, FulfillmentUpdate(status=OrderStatus.PROCESSING), fulfillment, None
    )
    assert processing.status == OrderStatus.PROCESSING
