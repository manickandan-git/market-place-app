from decimal import Decimal
from uuid import uuid4

from app.models.catalog import Product, ProductStatus, ProductVariant


def test_product_defaults_are_domain_safe() -> None:
    product = Product(
        owner_user_id=uuid4(),
        category_id=uuid4(),
        name="Desk",
        slug="desk",
    )
    assert product.status is None or product.status == ProductStatus.DRAFT


def test_variant_accepts_decimal_price() -> None:
    variant = ProductVariant(
        product_id=uuid4(),
        sku="DESK-1",
        name="Standard",
        price_amount=Decimal("129.99"),
    )
    assert variant.price_amount == Decimal("129.99")

