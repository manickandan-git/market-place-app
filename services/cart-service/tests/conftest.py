import os
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://cart:cart@localhost:5435/cart_service"
)

from app.config import Settings
from app.dependencies.auth import (
    Principal,
    get_current_principal,
    get_optional_principal,
)
from app.main import app
from app.models import Base
from app.repositories import CartRepository
from app.routes.dependencies import get_cart_service
from app.schemas.cart import ProductSnapshot
from app.services import CartService


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(_type, compiler, **kw):
    return compiler.visit_JSON(JSON(), **kw)


BUYER_ID = uuid4()
PRODUCT_ID = uuid4()
VARIANT_ID = uuid4()
ORDER_ID = uuid4()


class FakeProducts:
    price = Decimal("19.99")
    version = 1

    async def get_snapshot(self, product_id, variant_id, request_id):
        assert product_id == PRODUCT_ID
        assert variant_id == VARIANT_ID
        return ProductSnapshot(
            product_id=product_id,
            variant_id=variant_id,
            sku="TEST-SKU-001",
            product_name="Test Product",
            variant_name="Blue",
            image_url="https://example.com/product.png",
            unit_price=self.price,
            currency_code="USD",
            product_version=self.version,
        )


class FakeInventory:
    available = 20

    async def availability(self, sku, quantity, request_id):
        assert sku == "TEST-SKU-001"
        return self.available, self.available >= quantity


@pytest_asyncio.fixture
async def test_context():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    products = FakeProducts()
    inventory = FakeInventory()
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        max_item_quantity=100,
        max_distinct_items=100,
    )

    async def service_override():
        async with factory() as session:
            yield CartService(CartRepository(session), settings, products, inventory)

    async def buyer_override():
        return Principal(
            subject=BUYER_ID,
            roles=frozenset({"buyer"}),
            scopes=frozenset(),
            claims={"sub": str(BUYER_ID), "roles": ["buyer"]},
        )

    app.dependency_overrides[get_cart_service] = service_override
    app.dependency_overrides[get_optional_principal] = buyer_override
    app.dependency_overrides[get_current_principal] = buyer_override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, products, inventory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_context):
    return test_context[0]


@pytest_asyncio.fixture
async def guest_context(test_context):
    client, products, inventory = test_context

    async def anonymous_override():
        return None

    app.dependency_overrides[get_optional_principal] = anonymous_override
    return client, products, inventory


def add_payload(quantity: int = 2) -> dict:
    return {
        "product_id": str(PRODUCT_ID),
        "variant_id": str(VARIANT_ID),
        "quantity": quantity,
    }
