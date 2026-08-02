from __future__ import annotations

import pytest
import pytest_asyncio

from integration_tests.auth import Persona, resolve_token
from integration_tests.clients import MarketplaceClients
from integration_tests.config import Settings, get_settings


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

