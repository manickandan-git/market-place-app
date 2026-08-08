from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    prefix: str
    upstream_setting: str  # attribute name on Settings holding the base URL


# Pure allowlist: only a path matching one of these prefixes is proxied.
# Everything else — every `/api/v1/internal/...` path (cart, inventory,
# order all use that literal segment), `/api/v1/auth/service-token`, health
# checks, and any path nobody has written a rule for — resolves to None and
# 404s. There is no separate "blocked" list: a route not being here IS the
# block. This is deliberate — see services/api-gateway/docs/route-allowlist.md
# for the per-service audit this table is derived from, and don't add an
# entry here without updating that doc alongside it.
#
# notification-service has no entries at all: every one of its routes
# requires a static X-Internal-API-Key, not a user JWT, so it has nothing
# for the gateway to expose.
ALLOWLIST: tuple[Route, ...] = (
    # auth-service
    Route("/.well-known/jwks.json", "auth_service_url"),
    Route("/api/v1/auth/register", "auth_service_url"),
    Route("/api/v1/auth/verify-email", "auth_service_url"),
    Route("/api/v1/auth/resend-verification", "auth_service_url"),
    Route("/api/v1/auth/login", "auth_service_url"),
    Route("/api/v1/auth/token", "auth_service_url"),
    Route("/api/v1/auth/refresh", "auth_service_url"),
    Route("/api/v1/auth/logout", "auth_service_url"),
    Route("/api/v1/auth/forgot-password", "auth_service_url"),
    Route("/api/v1/auth/reset-password", "auth_service_url"),
    Route("/api/v1/auth/change-password", "auth_service_url"),
    Route("/api/v1/auth/sessions", "auth_service_url"),
    Route("/api/v1/users/me", "auth_service_url"),
    # `/api/v1/auth/service-token` is intentionally absent — client-credentials
    # exchange for trusted services only, never exposed to end users.
    # user-service
    Route("/api/v1/me", "user_service_url"),
    Route("/api/v1/sellers", "user_service_url"),
    # product-service
    Route("/api/v1/categories", "product_service_url"),
    Route("/api/v1/admin/categories", "product_service_url"),
    Route("/api/v1/products", "product_service_url"),
    Route("/api/v1/seller/products", "product_service_url"),
    # inventory-service
    Route("/api/v1/availability", "inventory_service_url"),
    Route("/api/v1/admin/warehouses", "inventory_service_url"),
    Route("/api/v1/seller/inventory", "inventory_service_url"),
    Route("/api/v1/reservations", "inventory_service_url"),
    # `/api/v1/internal/catalog-skus/...` and `/api/v1/internal/checkout/...`
    # are intentionally absent — see the ⚠️ note in route-allowlist.md: the
    # checkout-batch routes are also missing their inventory:checkout scope
    # gate service-side, so this block is a mitigation, not a full fix.
    # cart-service
    Route("/api/v1/guest-carts", "cart_service_url"),
    Route("/api/v1/cart", "cart_service_url"),
    # order-service
    Route("/api/v1/orders", "order_service_url"),
    # payment-service
    Route("/api/v1/payments", "payment_service_url"),
    Route("/api/v1/webhooks/stripe", "payment_service_url"),
    # shipping-service
    Route("/api/v1/shipments", "shipping_service_url"),
    # assistant-service
    Route("/api/v1/assistant", "assistant_service_url"),
)


def resolve(path: str) -> Route | None:
    """Longest-prefix match against the allowlist. None means 404 the request."""
    match: Route | None = None
    for route in ALLOWLIST:
        if path == route.prefix or path.startswith(route.prefix + "/"):
            if match is None or len(route.prefix) > len(match.prefix):
                match = route
    return match
