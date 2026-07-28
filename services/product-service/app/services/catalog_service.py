import hashlib
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import Principal
from app.exceptions import ServiceError
from app.models.catalog import (
    Category,
    Product,
    ProductImage,
    ProductStatus,
    ProductVariant,
)
from app.models.reliability import AuditLog, IdempotencyRecord, OutboxEvent
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.catalog import (
    CategoryCreate,
    CategoryUpdate,
    ImageCreate,
    ProductCreate,
    ProductUpdate,
    VariantCreate,
    VariantUpdate,
)


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CatalogRepository(session)

    @staticmethod
    def _can_manage(product: Product, principal: Principal) -> bool:
        return principal.has_role("admin") or product.owner_user_id == principal.subject

    @staticmethod
    def _snapshot(obj: Any) -> dict:
        values = {}
        for column in obj.__table__.columns:
            value = getattr(obj, column.name)
            values[column.name] = jsonable_encoder(value)
        return values

    def _audit(
        self,
        *,
        principal: Principal,
        action: str,
        resource_type: str,
        resource_id: UUID,
        before: dict | None,
        after: dict | None,
        request_id: str | None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=principal.subject,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                before_data=before,
                after_data=after,
                request_id=request_id,
            )
        )

    def _event(self, event_type: str, product: Product) -> None:
        self.session.add(
            OutboxEvent(
                aggregate_type="product",
                aggregate_id=product.id,
                event_type=event_type,
                payload={
                    "event_version": 1,
                    "product_id": str(product.id),
                    "owner_user_id": str(product.owner_user_id),
                    "category_id": str(product.category_id),
                    "status": product.status.value,
                    "version": product.version,
                },
            )
        )

    async def create_category(
        self,
        data: CategoryCreate,
        principal: Principal,
        request_id: str | None,
    ) -> Category:
        if data.parent_id and not await self.repo.get_category(data.parent_id):
            raise ServiceError(422, "invalid_parent", "Parent category does not exist")
        if await self.repo.get_category_by_slug(data.slug):
            raise ServiceError(409, "slug_taken", "Category slug is already in use")
        category = Category(**data.model_dump())
        self.session.add(category)
        await self.session.flush()
        self._audit(
            principal=principal,
            action="category.created",
            resource_type="category",
            resource_id=category.id,
            before=None,
            after=self._snapshot(category),
            request_id=request_id,
        )
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def update_category(
        self,
        category_id: UUID,
        data: CategoryUpdate,
        expected_version: int,
        principal: Principal,
        request_id: str | None,
    ) -> Category:
        category = await self.repo.get_category(category_id)
        if not category:
            raise ServiceError(404, "category_not_found", "Category was not found")
        if category.version != expected_version:
            raise ServiceError(412, "version_conflict", "Category version has changed")
        if data.parent_id == category_id:
            raise ServiceError(
                422,
                "invalid_parent",
                "Category cannot be its own parent",
            )
        if data.parent_id and not await self.repo.get_category(data.parent_id):
            raise ServiceError(422, "invalid_parent", "Parent category does not exist")
        if data.slug and data.slug != category.slug:
            existing = await self.repo.get_category_by_slug(data.slug)
            if existing and existing.id != category.id:
                raise ServiceError(409, "slug_taken", "Category slug is already in use")
        before = self._snapshot(category)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(category, field, value)
        category.version += 1
        await self.session.flush()
        # updated_at is server-computed (onupdate=func.now()); after an
        # UPDATE flush it's expired, and a plain getattr() in _snapshot()
        # would try to lazy-load it outside the async-aware context and
        # crash with MissingGreenlet. refresh() reloads it properly.
        await self.session.refresh(category)
        self._audit(
            principal=principal,
            action="category.updated",
            resource_type="category",
            resource_id=category.id,
            before=before,
            after=self._snapshot(category),
            request_id=request_id,
        )
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def create_product(
        self,
        data: ProductCreate,
        principal: Principal,
        request_id: str | None,
        idempotency_key: str | None,
    ) -> Product:
        request_hash = hashlib.sha256(
            data.model_dump_json().encode("utf-8")
        ).hexdigest()
        if idempotency_key:
            existing = await self.session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.actor_id == principal.subject,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise ServiceError(
                        409,
                        "idempotency_conflict",
                        "Idempotency key was reused with another request",
                    )
                product = await self.repo.get_product(existing.resource_id)
                if product:
                    return product

        category = await self.repo.get_category(data.category_id)
        if not category or not category.is_active:
            raise ServiceError(422, "invalid_category", "Active category was not found")
        if await self.repo.get_product_by_slug(data.slug):
            raise ServiceError(409, "slug_taken", "Product slug is already in use")
        for variant in data.variants:
            if await self.repo.get_variant_by_sku(variant.sku):
                raise ServiceError(409, "sku_taken", "SKU is already in use")
        core = data.model_dump(exclude={"variants", "images"})
        product = Product(owner_user_id=principal.subject, **core)
        product.variants = [
            ProductVariant(**variant.model_dump()) for variant in data.variants
        ]
        product.images = [
            ProductImage(
                url=str(image.url),
                alt_text=image.alt_text,
                sort_order=image.sort_order,
            )
            for image in data.images
        ]
        self.session.add(product)
        await self.session.flush()
        self._audit(
            principal=principal,
            action="product.created",
            resource_type="product",
            resource_id=product.id,
            before=None,
            after=self._snapshot(product),
            request_id=request_id,
        )
        self._event("catalog.product.created.v1", product)
        if idempotency_key:
            self.session.add(
                IdempotencyRecord(
                    actor_id=principal.subject,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    resource_id=product.id,
                )
            )
        await self.session.commit()
        return await self.repo.get_product(product.id)

    async def update_product(
        self,
        product_id: UUID,
        data: ProductUpdate,
        expected_version: int,
        principal: Principal,
        request_id: str | None,
    ) -> Product:
        product = await self._managed_product(product_id, principal, for_update=True)
        self._check_version(product, expected_version)
        if data.category_id:
            category = await self.repo.get_category(data.category_id)
            if not category or not category.is_active:
                raise ServiceError(422, "invalid_category", "Active category not found")
        if data.slug and data.slug != product.slug:
            existing = await self.repo.get_product_by_slug(data.slug)
            if existing and existing.id != product.id:
                raise ServiceError(409, "slug_taken", "Product slug is already in use")
        before = self._snapshot(product)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        product.version += 1
        await self.session.flush()
        # See update_category for why this refresh is required before
        # re-snapshotting a just-updated row (expired server-computed
        # updated_at would otherwise crash with MissingGreenlet).
        await self.session.refresh(product)
        self._audit(
            principal=principal,
            action="product.updated",
            resource_type="product",
            resource_id=product.id,
            before=before,
            after=self._snapshot(product),
            request_id=request_id,
        )
        self._event("catalog.product.updated.v1", product)
        await self.session.commit()
        return await self.repo.get_product(product.id)

    async def change_status(
        self,
        product_id: UUID,
        target: ProductStatus,
        expected_version: int,
        principal: Principal,
        request_id: str | None,
    ) -> Product:
        product = await self._managed_product(product_id, principal, for_update=True)
        self._check_version(product, expected_version)
        transitions = {
            ProductStatus.DRAFT: {ProductStatus.ACTIVE, ProductStatus.ARCHIVED},
            ProductStatus.ACTIVE: {ProductStatus.INACTIVE, ProductStatus.ARCHIVED},
            ProductStatus.INACTIVE: {ProductStatus.ACTIVE, ProductStatus.ARCHIVED},
            ProductStatus.ARCHIVED: set(),
        }
        if target not in transitions[product.status]:
            raise ServiceError(
                409,
                "invalid_status_transition",
                f"Cannot change {product.status.value} to {target.value}",
            )
        if target == ProductStatus.ACTIVE:
            active_variants = [item for item in product.variants if item.is_active]
            if not active_variants:
                raise ServiceError(
                    422,
                    "product_not_publishable",
                    "An active product requires at least one active variant",
                )
        before = self._snapshot(product)
        product.status = target
        product.version += 1
        await self.session.flush()
        # See update_category for why this refresh is required before
        # re-snapshotting a just-updated row.
        await self.session.refresh(product)
        self._audit(
            principal=principal,
            action="product.status_changed",
            resource_type="product",
            resource_id=product.id,
            before=before,
            after=self._snapshot(product),
            request_id=request_id,
        )
        self._event(f"catalog.product.{target.value}.v1", product)
        await self.session.commit()
        return await self.repo.get_product(product.id)

    async def add_variant(
        self,
        product_id: UUID,
        data: VariantCreate,
        principal: Principal,
        request_id: str | None,
    ) -> ProductVariant:
        product = await self._managed_product(product_id, principal)
        if await self.repo.get_variant_by_sku(data.sku):
            raise ServiceError(409, "sku_taken", "SKU is already in use")
        variant = ProductVariant(product_id=product.id, **data.model_dump())
        self.session.add(variant)
        await self.session.flush()
        self._audit(
            principal=principal,
            action="variant.created",
            resource_type="product_variant",
            resource_id=variant.id,
            before=None,
            after=self._snapshot(variant),
            request_id=request_id,
        )
        self._event("catalog.product.variant_changed.v1", product)
        await self.session.commit()
        await self.session.refresh(variant)
        return variant

    async def update_variant(
        self,
        product_id: UUID,
        variant_id: UUID,
        data: VariantUpdate,
        expected_version: int,
        principal: Principal,
        request_id: str | None,
    ) -> ProductVariant:
        product = await self._managed_product(product_id, principal)
        variant = await self.repo.get_variant(product_id, variant_id, for_update=True)
        if not variant:
            raise ServiceError(404, "variant_not_found", "Variant was not found")
        self._check_version(variant, expected_version)
        if data.sku and data.sku != variant.sku:
            existing = await self.repo.get_variant_by_sku(data.sku)
            if existing and existing.id != variant.id:
                raise ServiceError(409, "sku_taken", "SKU is already in use")
        before = self._snapshot(variant)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(variant, field, value)
        if (
            variant.compare_at_price is not None
            and variant.compare_at_price < variant.price_amount
        ):
            raise ServiceError(
                422,
                "invalid_compare_price",
                "compare_at_price must be at least price_amount",
            )
        variant.version += 1
        await self.session.flush()
        # See update_category for why this refresh is required before
        # re-snapshotting a just-updated row.
        await self.session.refresh(variant)
        self._audit(
            principal=principal,
            action="variant.updated",
            resource_type="product_variant",
            resource_id=variant.id,
            before=before,
            after=self._snapshot(variant),
            request_id=request_id,
        )
        self._event("catalog.product.variant_changed.v1", product)
        await self.session.commit()
        await self.session.refresh(variant)
        return variant

    async def add_image(
        self,
        product_id: UUID,
        data: ImageCreate,
        principal: Principal,
        request_id: str | None,
    ) -> ProductImage:
        product = await self._managed_product(product_id, principal)
        if await self.repo.image_sort_order_exists(product.id, data.sort_order):
            raise ServiceError(
                409, "sort_order_taken", "An image already exists at this sort_order"
            )
        image = ProductImage(
            product_id=product.id,
            url=str(data.url),
            alt_text=data.alt_text,
            sort_order=data.sort_order,
        )
        self.session.add(image)
        await self.session.flush()
        self._audit(
            principal=principal,
            action="image.created",
            resource_type="product_image",
            resource_id=image.id,
            before=None,
            after=self._snapshot(image),
            request_id=request_id,
        )
        self._event("catalog.product.image_changed.v1", product)
        await self.session.commit()
        await self.session.refresh(image)
        return image

    async def delete_image(
        self,
        product_id: UUID,
        image_id: UUID,
        principal: Principal,
        request_id: str | None,
    ) -> None:
        product = await self._managed_product(product_id, principal)
        image = next((item for item in product.images if item.id == image_id), None)
        if not image:
            raise ServiceError(404, "image_not_found", "Image was not found")
        before = self._snapshot(image)
        await self.session.delete(image)
        self._audit(
            principal=principal,
            action="image.deleted",
            resource_type="product_image",
            resource_id=image.id,
            before=before,
            after=None,
            request_id=request_id,
        )
        self._event("catalog.product.image_changed.v1", product)
        await self.session.commit()

    async def _managed_product(
        self,
        product_id: UUID,
        principal: Principal,
        *,
        for_update: bool = False,
    ) -> Product:
        product = await self.repo.get_product(product_id, for_update=for_update)
        if not product or not self._can_manage(product, principal):
            # Ownership and not-found are indistinguishable by design: a
            # distinct 403 would let a caller learn that a given ID belongs
            # to another seller.
            raise ServiceError(404, "product_not_found", "Product was not found")
        return product

    @staticmethod
    def _check_version(resource: Any, expected: int) -> None:
        if resource.version != expected:
            raise ServiceError(412, "version_conflict", "Resource version has changed")
