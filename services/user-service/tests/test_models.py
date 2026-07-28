from app.models import Base


def test_expected_tables_are_registered() -> None:
    assert {
        "addresses",
        "audit_logs",
        "buyer_profiles",
        "idempotency_records",
        "notification_preferences",
        "outbox_events",
        "privacy_requests",
        "seller_profiles",
        "user_consents",
        "user_preferences",
    } == set(Base.metadata.tables)
