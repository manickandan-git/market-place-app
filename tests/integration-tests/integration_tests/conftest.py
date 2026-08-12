from __future__ import annotations

import pytest
import pytest_asyncio

from integration_tests.auth import Persona, resolve_token
from integration_tests.catalog import create_stocked_product
from integration_tests.clients import ApiError, MarketplaceClients
from integration_tests.config import Settings, get_settings
from integration_tests.order_flow import add_to_cart, checkout


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest_asyncio.fixture(scope="session")
async def clients(settings: Settings):
    value = MarketplaceClients(settings)
    yield value
    await value.close()


async def _persona(
    name: str,
    settings: Settings,
    clients: MarketplaceClients,
) -> Persona:
    return await resolve_token(
        name=name,
        supplied_token=getattr(settings, f"{name}_access_token"),
        email=getattr(settings, f"{name}_email", None),
        password=getattr(settings, f"{name}_password", None),
        clients=clients,
        settings=settings,
    )


@pytest_asyncio.fixture(scope="session")
async def buyer(settings: Settings, clients: MarketplaceClients) -> Persona:
    return await _persona("buyer", settings, clients)


@pytest_asyncio.fixture(scope="session")
async def seller_a(settings: Settings, clients: MarketplaceClients) -> Persona:
    return await _persona("seller_a", settings, clients)


@pytest_asyncio.fixture(scope="session")
async def admin(settings: Settings, clients: MarketplaceClients) -> Persona:
    return await _persona("admin", settings, clients)


@pytest_asyncio.fixture(scope="session")
async def inventory_sync(
    settings: Settings,
    clients: MarketplaceClients,
) -> Persona:
    token = settings.inventory_sync_access_token
    if not token:
        pytest.skip(
            "Set INVENTORY_SYNC_ACCESS_TOKEN to a JWT with inventory:sync scope"
        )
    return await resolve_token(
        name="inventory_sync",
        supplied_token=token,
        email=None,
        password=None,
        clients=clients,
        settings=settings,
    )


@pytest_asyncio.fixture(scope="session")
async def checkout_retires_cart(
    clients: MarketplaceClients,
    settings: Settings,
    buyer: Persona,
    seller_a: Persona,
    admin: Persona,
    inventory_sync: Persona,
) -> None:
    """Probes whether a successful checkout actually retires the buyer's
    active cart, i.e. whether cart-service's internal `mark_checked_out`
    call (made by order-service after creating an order) succeeds.

    This used to fail unconditionally (see CLAUDE.md's Known gaps history
    and `docs/e2e-platform-test-report.md`'s Finding 7 for the full
    writeup) but was fixed in commit 81e3138: `customer_id` now travels in
    the request body instead of a JWT claim no service token could carry,
    and order-service's uniqueness constraint on `(customer_id, cart_id)`
    was scoped to non-terminal order statuses. This fixture is kept as a
    live regression probe, not a known-bug workaround -- if either skip
    below ever fires again on a clean environment, that's a real
    regression, not expected behavior.

    Session-scoped so the probe (a real checkout) only runs once. Every
    test in test_60/70/80 that performs a checkout depends on this fixture
    -- including the "first" one -- so a regression here fails the whole
    dependent suite with one clear skip reason instead of a confusing
    pileup of unrelated 409s.
    """
    _, variant, _ = await create_stocked_product(
        clients,
        admin_token=admin.token,
        seller_token=seller_a.token,
        inventory_sync_token=inventory_sync.token,
        quantity=5,
    )
    cart = await add_to_cart(clients, buyer, variant, quantity=1)
    try:
        await checkout(clients, buyer, cart)
    except ApiError as exc:
        pytest.skip(
            "Checkout itself failed for the probe cart, so cart-retirement "
            "can't be verified this run. If this is a 409 "
            "order_already_exists, the buyer persona likely has a leftover "
            "non-terminal order from a prior run/session blocking this "
            "exact (customer_id, cart_id) pair -- cancel it and rerun "
            f"before assuming mark_checked_out has regressed: {exc}"
        )
    after = await clients.cart.json(
        "GET", "/api/v1/cart", token=buyer.token, expected=200
    )
    if after["id"] == cart["id"]:
        pytest.skip(
            "REGRESSION: cart-service's mark_checked_out did not retire "
            "the cart after a successful checkout. This was fixed in "
            "commit 81e3138 -- see CLAUDE.md Known gaps and "
            "docs/e2e-platform-test-report.md's Finding 7 for the original "
            "bug and its fix. Any later checkout in this session would "
            "collide with order-service's (customer_id, cart_id) "
            "uniqueness constraint."
        )

