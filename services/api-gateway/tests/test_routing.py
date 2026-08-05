from app.services.routing import resolve


def test_public_routes_resolve_to_correct_service():
    assert resolve("/api/v1/products").upstream_setting == "product_service_url"
    assert resolve("/api/v1/cart").upstream_setting == "cart_service_url"
    assert resolve("/api/v1/orders").upstream_setting == "order_service_url"
    assert resolve("/api/v1/payments").upstream_setting == "payment_service_url"
    assert resolve("/api/v1/shipments").upstream_setting == "shipping_service_url"
    assert resolve("/.well-known/jwks.json").upstream_setting == "auth_service_url"


def test_nested_paths_resolve_via_longest_prefix():
    assert resolve("/api/v1/cart/items/123").upstream_setting == "cart_service_url"
    assert (
        resolve("/api/v1/seller/products/1/variants/2").upstream_setting
        == "product_service_url"
    )
    assert (
        resolve("/api/v1/seller/inventory/1/movements").upstream_setting
        == "inventory_service_url"
    )
    assert (
        resolve("/api/v1/admin/categories/1").upstream_setting
        == "product_service_url"
    )
    assert (
        resolve("/api/v1/admin/warehouses/1").upstream_setting
        == "inventory_service_url"
    )
    assert (
        resolve("/api/v1/auth/sessions/abc-123").upstream_setting
        == "auth_service_url"
    )
    assert resolve("/api/v1/users/me/audit-events").upstream_setting == (
        "auth_service_url"
    )


def test_internal_paths_are_blocked_by_omission():
    assert resolve("/api/v1/internal/orders/1/payment-authorized") is None
    assert resolve("/api/v1/internal/orders/1/fulfillment") is None
    assert resolve("/api/v1/internal/carts/1/checked-out") is None
    assert resolve("/api/v1/internal/carts/expire") is None
    assert resolve("/api/v1/internal/checkout/reservations/batch") is None
    assert resolve("/api/v1/internal/checkout/reservations/1/commit") is None
    assert resolve("/api/v1/internal/checkout/reservations/1/release") is None
    assert resolve("/api/v1/internal/reservations/expire") is None
    assert resolve("/api/v1/internal/catalog-skus/1") is None


def test_service_token_is_blocked():
    assert resolve("/api/v1/auth/service-token") is None


def test_unknown_path_is_blocked():
    assert resolve("/api/v1/does-not-exist") is None
    assert resolve("/") is None


def test_notification_service_has_no_route():
    # notification-service is never registered — its routes require a
    # static X-Internal-API-Key, not a user JWT, so nothing should resolve
    # to it regardless of path shape.
    from app.services.routing import ALLOWLIST

    assert all(
        route.upstream_setting != "notification_service_url" for route in ALLOWLIST
    )
