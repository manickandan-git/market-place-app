from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.catalog import (
    CategoryCreate,
    ProductCreate,
    ProductUpdate,
    VariantCreate,
)
from app.schemas.common import PaginatedResponse


def test_category_slug_is_normalized() -> None:
    category = CategoryCreate(name="Home Office", slug="Home-Office")
    assert category.slug == "home-office"


def test_product_slug_is_normalized() -> None:
    product = ProductCreate(
        category_id=uuid4(),
        name="Mechanical Keyboard",
        slug="Mechanical-Keyboard",
    )
    assert product.slug == "mechanical-keyboard"


def test_variant_codes_are_normalized() -> None:
    variant = VariantCreate(
        sku=" key-001 ",
        name="Black",
        price_amount="49.99",
        currency_code="usd",
    )
    assert variant.sku == "KEY-001"
    assert variant.currency_code == "USD"


def test_variant_rejects_invalid_compare_price() -> None:
    with pytest.raises(ValidationError):
        VariantCreate(
            sku="KEY-001",
            name="Black",
            price_amount=Decimal("49.99"),
            compare_at_price=Decimal("39.99"),
        )


def test_product_rejects_duplicate_nested_skus() -> None:
    with pytest.raises(ValidationError):
        ProductCreate(
            category_id=uuid4(),
            name="Keyboard",
            slug="keyboard",
            variants=[
                VariantCreate(sku="SKU-1", name="One", price_amount="1.00"),
                VariantCreate(sku="sku-1", name="Two", price_amount="2.00"),
            ],
        )


def test_empty_product_patch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProductUpdate()


def test_pagination_metadata() -> None:
    page = PaginatedResponse[str].create(
        items=["a"],
        page=2,
        page_size=10,
        total_items=21,
    )
    assert page.pagination.total_pages == 3

