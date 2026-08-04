from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.config import Settings
from app.dependencies.auth import Principal
from app.exceptions import ServiceError
from app.models.payment import PaymentStatus, RefundStatus
from app.schemas.payment import PaymentCreate, RefundCreate
from app.services.order_client import OrderSnapshot
from app.services.payment_service import PaymentService
from app.services.stripe_client import StripePaymentIntent


class FakeStripeClient:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.refunds: list[dict] = []
        self._counter = 0

    async def create_payment_intent(self, amount, currency_code, metadata):
        self._counter += 1
        pi_id = f"pi_test_{self._counter}"
        self.created.append(
            {
                "id": pi_id,
                "amount": amount,
                "currency_code": currency_code,
                "metadata": metadata,
            }
        )
        return StripePaymentIntent(
            id=pi_id, client_secret=f"{pi_id}_secret", status="requires_payment_method"
        )

    async def create_refund(self, payment_intent_id, amount):
        self._counter += 1
        refund_id = f"re_test_{self._counter}"
        self.refunds.append({"payment_intent_id": payment_intent_id, "amount": amount})
        return refund_id


class FakeOrderClient:
    def __init__(
        self, order_id, grand_total, currency_code="USD", status="pending_payment"
    ):
        self.order_id = order_id
        self.grand_total = grand_total
        self.currency_code = currency_code
        self.status = status
        self.authorized_calls: list[dict] = []
        self.failed_calls: list[dict] = []
        self.refunded_calls: list[dict] = []
        self.fail_refund_callback = False

    async def get_order(self, order_id, buyer_token, request_id):
        if order_id != self.order_id:
            raise ServiceError(404, "order_not_found", "Order was not found")
        return OrderSnapshot(
            order_id=order_id,
            status=self.status,
            grand_total=self.grand_total,
            currency_code=self.currency_code,
        )

    async def payment_authorized(
        self,
        order_id,
        payment_reference,
        amount,
        currency_code,
        service_token,
        request_id,
    ):
        self.authorized_calls.append(
            {
                "order_id": order_id,
                "payment_reference": payment_reference,
                "amount": amount,
                "currency_code": currency_code,
            }
        )

    async def payment_failed(
        self, order_id, payment_reference, reason, service_token, request_id
    ):
        self.failed_calls.append(
            {
                "order_id": order_id,
                "payment_reference": payment_reference,
                "reason": reason,
            }
        )

    async def payment_refunded(
        self,
        order_id,
        refunded_amount,
        currency_code,
        reason,
        service_token,
        request_id,
    ):
        if self.fail_refund_callback:
            raise ServiceError(
                502, "order_callback_failed", "Order Service callback failed"
            )
        self.refunded_calls.append(
            {
                "order_id": order_id,
                "refunded_amount": refunded_amount,
                "currency_code": currency_code,
                "reason": reason,
            }
        )


class FakeAuthClient:
    async def service_token(self):
        return "fake-service-token"


def principal(*, subject=None, roles=("buyer",)) -> Principal:
    return Principal(
        subject=subject or uuid4(),
        roles=frozenset(roles),
        scopes=frozenset(),
        claims={},
    )


def make_event(event_id, event_type, intent_id, **intent_extra):
    intent = SimpleNamespace(id=intent_id, **intent_extra)
    return SimpleNamespace(
        id=event_id, type=event_type, data=SimpleNamespace(object=intent)
    )


def build_service(session, order_client=None, stripe_client=None):
    stripe_client = stripe_client or FakeStripeClient()
    order_client = order_client or FakeOrderClient(uuid4(), Decimal("39.98"))
    service = PaymentService(
        session,
        Settings(),
        stripe_client,
        order_client,
        FakeAuthClient(),
    )
    return service, stripe_client, order_client


# ---------------------------------------------------------------------------
# create_payment
# ---------------------------------------------------------------------------


async def test_create_payment_creates_pending_payment(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("39.98"))
    service, stripe, _ = build_service(session, order_client=order_client)
    buyer = principal()

    payment, client_secret = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), buyer, "buyer-token", None, None
    )

    assert payment.status == PaymentStatus.PENDING
    assert payment.amount == Decimal("39.98")
    assert payment.customer_id == buyer.subject
    assert client_secret == f"{stripe.created[0]['id']}_secret"
    assert stripe.created[0]["amount"] == Decimal("39.98")


async def test_create_payment_rejects_duplicate_for_order(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("10.00"))
    service, _, _ = build_service(session, order_client=order_client)
    buyer = principal()
    data = PaymentCreate(order_id=order_client.order_id)

    await service.create_payment(data, buyer, "token", None, None)
    with pytest.raises(ServiceError) as error:
        await service.create_payment(data, principal(), "token", None, None)
    assert error.value.code == "payment_already_exists"


async def test_create_payment_rejects_non_pending_order(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("10.00"), status="confirmed")
    service, _, _ = build_service(session, order_client=order_client)

    with pytest.raises(ServiceError) as error:
        await service.create_payment(
            PaymentCreate(order_id=order_client.order_id),
            principal(),
            "token",
            None,
            None,
        )
    assert error.value.code == "order_not_payable"


async def test_create_payment_is_idempotent(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("25.00"))
    service, stripe, _ = build_service(session, order_client=order_client)
    buyer = principal()
    data = PaymentCreate(order_id=order_client.order_id)

    payment, secret = await service.create_payment(data, buyer, "token", "key-1", None)
    replay, replay_secret = await service.create_payment(
        data, buyer, "token", "key-1", None
    )

    assert replay.id == payment.id
    assert replay_secret is None
    assert len(stripe.created) == 1


# ---------------------------------------------------------------------------
# get_payment
# ---------------------------------------------------------------------------


async def test_get_payment_hides_other_customers_payment(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("10.00"))
    service, _, _ = build_service(session, order_client=order_client)
    buyer = principal()
    payment, _ = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), buyer, "token", None, None
    )

    stranger = principal()
    with pytest.raises(ServiceError) as error:
        await service.get_payment(payment.id, stranger)
    assert error.value.code == "payment_not_found"

    fetched = await service.get_payment(payment.id, buyer)
    assert fetched.id == payment.id


# ---------------------------------------------------------------------------
# webhook handling
# ---------------------------------------------------------------------------


async def test_webhook_success_marks_payment_and_calls_order(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("39.98"))
    service, stripe, _ = build_service(session, order_client=order_client)
    payment, _ = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), principal(), "token", None, None
    )
    intent_id = stripe.created[0]["id"]

    await service.handle_webhook_event(
        make_event("evt_1", "payment_intent.succeeded", intent_id), None
    )

    updated = await service.get_payment(
        payment.id, principal(subject=payment.customer_id)
    )
    assert updated.status == PaymentStatus.SUCCEEDED
    assert len(order_client.authorized_calls) == 1
    assert order_client.authorized_calls[0]["order_id"] == order_client.order_id
    assert order_client.authorized_calls[0]["amount"] == Decimal("39.98")


async def test_webhook_failure_marks_payment_and_calls_order(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("15.00"))
    service, stripe, _ = build_service(session, order_client=order_client)
    payment, _ = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), principal(), "token", None, None
    )
    intent_id = stripe.created[0]["id"]

    await service.handle_webhook_event(
        make_event(
            "evt_2",
            "payment_intent.payment_failed",
            intent_id,
            last_payment_error=SimpleNamespace(message="Your card was declined."),
        ),
        None,
    )

    updated = await service.get_payment(
        payment.id, principal(subject=payment.customer_id)
    )
    assert updated.status == PaymentStatus.FAILED
    assert updated.failure_reason == "Your card was declined."
    assert len(order_client.failed_calls) == 1


async def test_webhook_is_idempotent_by_event_id(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("15.00"))
    service, stripe, _ = build_service(session, order_client=order_client)
    await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), principal(), "token", None, None
    )
    intent_id = stripe.created[0]["id"]
    event = make_event("evt_3", "payment_intent.succeeded", intent_id)

    await service.handle_webhook_event(event, None)
    await service.handle_webhook_event(event, None)

    assert len(order_client.authorized_calls) == 1


async def test_webhook_ignores_unhandled_event_types(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("15.00"))
    service, stripe, _ = build_service(session, order_client=order_client)
    await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), principal(), "token", None, None
    )
    intent_id = stripe.created[0]["id"]

    await service.handle_webhook_event(
        make_event("evt_4", "charge.succeeded", intent_id), None
    )

    assert order_client.authorized_calls == []
    assert order_client.failed_calls == []


# ---------------------------------------------------------------------------
# refunds
# ---------------------------------------------------------------------------


async def test_full_refund_marks_payment_refunded(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("40.00"))
    service, stripe, _ = build_service(session, order_client=order_client)
    buyer = principal()
    payment, _ = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), buyer, "token", None, None
    )
    intent_id = stripe.created[0]["id"]
    await service.handle_webhook_event(
        make_event("evt_5", "payment_intent.succeeded", intent_id), None
    )

    refund = await service.create_refund(payment.id, RefundCreate(), buyer, None)

    assert refund.status == RefundStatus.SUCCEEDED
    assert refund.amount == Decimal("40.00")
    updated = await service.get_payment(payment.id, buyer)
    assert updated.status == PaymentStatus.REFUNDED
    assert len(order_client.refunded_calls) == 1
    assert order_client.refunded_calls[0]["refunded_amount"] == Decimal("40.00")


async def test_sequential_partial_refunds_report_cumulative_amount(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("40.00"))
    service, stripe, _ = build_service(session, order_client=order_client)
    buyer = principal()
    payment, _ = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), buyer, "token", None, None
    )
    intent_id = stripe.created[0]["id"]
    await service.handle_webhook_event(
        make_event("evt_5b", "payment_intent.succeeded", intent_id), None
    )

    await service.create_refund(
        payment.id, RefundCreate(amount=Decimal("15.00")), buyer, None
    )
    await service.create_refund(
        payment.id, RefundCreate(amount=Decimal("25.00")), buyer, None
    )

    assert [c["refunded_amount"] for c in order_client.refunded_calls] == [
        Decimal("15.00"),
        Decimal("40.00"),
    ]
    updated = await service.get_payment(payment.id, buyer)
    assert updated.status == PaymentStatus.REFUNDED


async def test_refund_survives_order_callback_failure(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("40.00"))
    order_client.fail_refund_callback = True
    service, stripe, _ = build_service(session, order_client=order_client)
    buyer = principal()
    payment, _ = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), buyer, "token", None, None
    )
    intent_id = stripe.created[0]["id"]
    await service.handle_webhook_event(
        make_event("evt_5c", "payment_intent.succeeded", intent_id), None
    )

    refund = await service.create_refund(payment.id, RefundCreate(), buyer, None)

    assert refund.status == RefundStatus.SUCCEEDED
    updated = await service.get_payment(payment.id, buyer)
    assert updated.status == PaymentStatus.REFUNDED
    assert order_client.refunded_calls == []


async def test_partial_refund_marks_payment_partially_refunded(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("40.00"))
    service, stripe, _ = build_service(session, order_client=order_client)
    buyer = principal()
    payment, _ = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), buyer, "token", None, None
    )
    intent_id = stripe.created[0]["id"]
    await service.handle_webhook_event(
        make_event("evt_6", "payment_intent.succeeded", intent_id), None
    )

    refund = await service.create_refund(
        payment.id, RefundCreate(amount=Decimal("15.00")), buyer, None
    )

    assert refund.amount == Decimal("15.00")
    updated = await service.get_payment(payment.id, buyer)
    assert updated.status == PaymentStatus.PARTIALLY_REFUNDED


async def test_refund_rejects_amount_exceeding_remaining(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("40.00"))
    service, stripe, _ = build_service(session, order_client=order_client)
    buyer = principal()
    payment, _ = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), buyer, "token", None, None
    )
    intent_id = stripe.created[0]["id"]
    await service.handle_webhook_event(
        make_event("evt_7", "payment_intent.succeeded", intent_id), None
    )

    with pytest.raises(ServiceError) as error:
        await service.create_refund(
            payment.id, RefundCreate(amount=Decimal("100.00")), buyer, None
        )
    assert error.value.code == "refund_exceeds_remaining"


async def test_refund_rejects_unsucceeded_payment(session) -> None:
    order_client = FakeOrderClient(uuid4(), Decimal("40.00"))
    service, _, _ = build_service(session, order_client=order_client)
    buyer = principal()
    payment, _ = await service.create_payment(
        PaymentCreate(order_id=order_client.order_id), buyer, "token", None, None
    )

    with pytest.raises(ServiceError) as error:
        await service.create_refund(payment.id, RefundCreate(), buyer, None)
    assert error.value.code == "payment_not_refundable"
