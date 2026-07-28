from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.dependencies.auth import Principal, require_roles
from app.dependencies.headers import optional_idempotency_key, required_version
from app.exceptions import ServiceError
from app.models.catalog import ProductStatus
from app.routes.dependencies import get_catalog_service
from app.schemas.catalog import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    ImageCreate,
    ImageResponse,
    ProductCreate,
    ProductResponse,
    ProductStatusUpdate,
    ProductSummary,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
    VariantUpdate,
)
from app.schemas.common import PaginatedResponse
from app.services.catalog_service import CatalogService

router = APIRouter()
SellerPrincipal = Annotated[Principal, Depends(require_roles("seller", "admin"))]
AdminPrincipal = Annotated[Principal, Depends(require_roles("admin"))]
Service = Annotated[CatalogService, Depends(get_catalog_service)]
Version = Annotated[int, Depends(required_version)]
IdempotencyKey = Annotated[str | None, Depends(optional_idempotency_key)]


@router.get("/categories", response_model=list[CategoryResponse], tags=["categories"])
async def list_categories(service: Service) -> list:
    return await service.repo.list_categories(active_only=True)


@router.post(
    "/admin/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["categories"],
)
async def create_category(
    data: CategoryCreate,
    request: Request,
    principal: AdminPrincipal,
    service: Service,
):
    return await service.create_category(
        data,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.patch(
    "/admin/categories/{category_id}",
    response_model=CategoryResponse,
    tags=["categories"],
)
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    request: Request,
    principal: AdminPrincipal,
    service: Service,
    expected_version: Version,
):
    return await service.update_category(
        category_id,
        data,
        expected_version,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/products",
    response_model=PaginatedResponse[ProductSummary],
    tags=["catalog"],
)
async def list_public_products(
    service: Service,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category_id: UUID | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=100),
):
    items, total = await service.repo.list_products(
        page=page,
        page_size=page_size,
        category_id=category_id,
        statuses={ProductStatus.ACTIVE},
        query=q,
    )
    return PaginatedResponse[ProductSummary].create(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total,
    )


@router.get("/products/{product_id}", response_model=ProductResponse, tags=["catalog"])
async def get_public_product(product_id: UUID, service: Service):
    product = await service.repo.get_product(product_id)
    if not product or product.status != ProductStatus.ACTIVE:
        raise ServiceError(404, "product_not_found", "Product was not found")
    return product


@router.get(
    "/products/by-slug/{slug}",
    response_model=ProductResponse,
    tags=["catalog"],
)
async def get_public_product_by_slug(slug: str, service: Service):
    product = await service.repo.get_product_by_slug(slug.lower())
    if not product or product.status != ProductStatus.ACTIVE:
        raise ServiceError(404, "product_not_found", "Product was not found")
    return product


@router.get(
    "/seller/products",
    response_model=PaginatedResponse[ProductSummary],
    tags=["seller catalog"],
)
async def list_seller_products(
    principal: SellerPrincipal,
    service: Service,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    product_status: ProductStatus | None = Query(default=None, alias="status"),
):
    items, total = await service.repo.list_products(
        page=page,
        page_size=page_size,
        owner_user_id=None if principal.has_role("admin") else principal.subject,
        statuses={product_status} if product_status else None,
    )
    return PaginatedResponse[ProductSummary].create(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total,
    )


@router.post(
    "/seller/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["seller catalog"],
)
async def create_product(
    data: ProductCreate,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
    idempotency_key: IdempotencyKey,
):
    return await service.create_product(
        data,
        principal,
        getattr(request.state, "request_id", None),
        idempotency_key,
    )


@router.get(
    "/seller/products/{product_id}",
    response_model=ProductResponse,
    tags=["seller catalog"],
)
async def get_managed_product(
    product_id: UUID,
    principal: SellerPrincipal,
    service: Service,
):
    return await service._managed_product(product_id, principal)


@router.patch(
    "/seller/products/{product_id}",
    response_model=ProductResponse,
    tags=["seller catalog"],
)
async def update_product(
    product_id: UUID,
    data: ProductUpdate,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
    expected_version: Version,
):
    return await service.update_product(
        product_id,
        data,
        expected_version,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.put(
    "/seller/products/{product_id}/status",
    response_model=ProductResponse,
    tags=["seller catalog"],
)
async def change_product_status(
    product_id: UUID,
    data: ProductStatusUpdate,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
    expected_version: Version,
):
    return await service.change_status(
        product_id,
        data.status,
        expected_version,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.post(
    "/seller/products/{product_id}/variants",
    response_model=VariantResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["variants"],
)
async def add_variant(
    product_id: UUID,
    data: VariantCreate,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
):
    return await service.add_variant(
        product_id,
        data,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.patch(
    "/seller/products/{product_id}/variants/{variant_id}",
    response_model=VariantResponse,
    tags=["variants"],
)
async def update_variant(
    product_id: UUID,
    variant_id: UUID,
    data: VariantUpdate,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
    expected_version: Version,
):
    return await service.update_variant(
        product_id,
        variant_id,
        data,
        expected_version,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.post(
    "/seller/products/{product_id}/images",
    response_model=ImageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["images"],
)
async def add_image(
    product_id: UUID,
    data: ImageCreate,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
):
    return await service.add_image(
        product_id,
        data,
        principal,
        getattr(request.state, "request_id", None),
    )


@router.delete(
    "/seller/products/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["images"],
)
async def delete_image(
    product_id: UUID,
    image_id: UUID,
    request: Request,
    principal: SellerPrincipal,
    service: Service,
) -> Response:
    await service.delete_image(
        product_id,
        image_id,
        principal,
        getattr(request.state, "request_id", None),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
