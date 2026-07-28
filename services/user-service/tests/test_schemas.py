import pytest
from pydantic import ValidationError

from app.schemas import (
    AddressCreate,
    AddressUpdate,
    ConsentsUpdate,
    NotificationPreferencesUpdate,
    PrivacyRequestCreate,
    SellerProfileCreate,
    UserPreferenceUpdate,
)


def test_address_normalizes_country() -> None:
    address = AddressCreate(
        address_type="shipping",
        recipient_name="John Doe",
        address_line1="123 Main Street",
        city="Atlanta",
        postal_code="30024",
        country_code="us",
    )
    assert address.country_code == "US"


def test_empty_address_patch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AddressUpdate()


def test_seller_slug_is_normalized() -> None:
    seller = SellerProfileCreate(business_name="Demo Store", store_slug="Demo-Store")
    assert seller.store_slug == "demo-store"


def test_invalid_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserPreferenceUpdate(time_zone="Not/A-Timezone")


def test_duplicate_notification_pair_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NotificationPreferencesUpdate(
            preferences=[
                {"channel": "email", "category": "orders", "is_enabled": True},
                {"channel": "email", "category": "orders", "is_enabled": False},
            ]
        )


def test_duplicate_consent_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ConsentsUpdate(
            consents=[
                {
                    "consent_type": "marketing",
                    "is_granted": True,
                    "policy_version": "1",
                },
                {
                    "consent_type": "marketing",
                    "is_granted": False,
                    "policy_version": "1",
                },
            ]
        )


def test_correction_requires_details() -> None:
    with pytest.raises(ValidationError):
        PrivacyRequestCreate(request_type="correction")
