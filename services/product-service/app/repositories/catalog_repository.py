from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import (
    Category,
    Product,
    ProductImage,
    ProductStatus,
    ProductVariant,
)


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_category(self, category_id: UUID) -> Category | None:
        return await self.session.get(Category, category_id)

    async def list_categories(self, active_only: bool = True) -> list[Category]:
        stmt = select(Category).order_by(Category.sort_order, Category.name)
        if active_only:
            stmt = stmt.where(Category.is_active.is_(True))
        return list((await self.session.scalars(stmt)).all())

    async def get_category_by_slug(self, slug: str) -> Category | None:
        stmt = select(Category).where(Category.slug == slug)
        return (await self.session.scalars(stmt)).one_or_none()

    async def get_product(
        self,
        product_id: UUID,
        *,
        for_update: bool = False,
    ) -> Product | None:
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.variants),
                selectinload(Product.images),
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).one_or_none()

    async def get_variant_by_sku(self, sku: str) -> ProductVariant | None:
        stmt = select(ProductVariant).where(ProductVariant.sku == sku)
        return (await self.session.scalars(stmt)).one_or_none()

    async def image_sort_order_exists(
        self, product_id: UUID, sort_order: int
    ) -> bool:
        stmt = select(ProductImage.id).where(
            ProductImage.product_id == product_id,
            ProductImage.sort_order == sort_order,
        )
        return (await self.session.scalars(stmt)).first() is not None

    async def get_product_by_slug(self, slug: str) -> Product | None:
        stmt = (
            select(Product)
            .where(Product.slug == slug)
            .options(
                selectinload(Product.variants),
                selectinload(Product.images),
            )
        )
        return (await self.session.scalars(stmt)).one_or_none()

    async def list_products(
        self,
        *,
        page: int,
        page_size: int,
        category_id: UUID | None = None,
        owner_user_id: UUID | None = None,
        statuses: set[ProductStatus] | None = None,
        query: str | None = None,
    ) -> tuple[list[Product], int]:
        filters = []
        if category_id:
            filters.append(Product.category_id == category_id)
        if owner_user_id:
            filters.append(Product.owner_user_id == owner_user_id)
        if statuses:
            filters.append(Product.status.in_(statuses))
        if query:
            filters.append(Product.name.ilike(f"%{query}%"))

        count_stmt = select(func.count(Product.id)).where(*filters)
        total = int((await self.session.scalar(count_stmt)) or 0)
        stmt = (
            select(Product)
            .where(*filters)
            .order_by(Product.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.scalars(stmt)).all()), total

    async def get_variant(
        self,
        product_id: UUID,
        variant_id: UUID,
        *,
        for_update: bool = False,
    ) -> ProductVariant | None:
        stmt = select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.product_id == product_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).one_or_none()

