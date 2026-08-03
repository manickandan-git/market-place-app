from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import OrderStatus
from app.schemas import AddressSnapshot, FulfillmentUpdate, PaymentAuthorized


def test_address_requires_two_letter_country() -> None:
    with pytest.raises(ValidationError):
        AddressSnapshot(
            full_name="Buyer",
            line1="1 Main St",
            city="Atlanta",
            state_or_region="GA",
            postal_code="30024",
            country_code="USA",
        )


def test_payment_authorization_requires_positive_amount() -> None:
    with pytest.raises(ValidationError):
        PaymentAuthorized(
            payment_reference=str(uuid4()),
            authorized_amount=Decimal("0"),
            currency_code="USD",
        )


@pytest.mark.parametrize(
    "value",
    [OrderStatus.PROCESSING, OrderStatus.SHIPPED, OrderStatus.DELIVERED],
)
def test_allowed_fulfillment_states(value: OrderStatus) -> None:
    assert FulfillmentUpdate(status=value).status == value


def test_reject_non_fulfillment_state() -> None:
    with pytest.raises(ValidationError):
        FulfillmentUpdate(status=OrderStatus.CANCELLED)
