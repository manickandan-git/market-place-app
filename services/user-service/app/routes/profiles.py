from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, Security, status

from app.dependencies import CurrentUser, get_current_user, parse_if_match, require_seller
from app.exceptions import NotFoundError
from app.routes.dependencies import get_user_service
from app.schemas import (
    BuyerProfileCreate,
    BuyerProfileResponse,
    BuyerProfileUpdate,
    PublicSellerProfile,
    SellerProfileCreate,
    SellerProfileResponse,
    SellerProfileUpdate,
)
from app.services import UserService

router = APIRouter(tags=["profiles"])


@router.post("/me", response_model=BuyerProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: BuyerProfileCreate,
    request: Request,
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.create_profile(
        user.user_id, payload, getattr(request.state, "correlation_id", None)
    )


@router.get("/me", response_model=BuyerProfileResponse)
async def get_profile(
    response: Response,
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    profile = await service.require_profile(user.user_id)
    response.headers["ETag"] = f'"{profile.version}"'
    return profile


@router.patch("/me", response_model=BuyerProfileResponse)
async def update_profile(
    payload: BuyerProfileUpdate,
    request: Request,
    response: Response,
    version: int = Depends(parse_if_match),
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    profile = await service.update_profile(
        user.user_id, payload, version, getattr(request.state, "correlation_id", None)
    )
    response.headers["ETag"] = f'"{profile.version}"'
    return profile


@router.put("/me/seller", response_model=SellerProfileResponse, status_code=201)
async def create_seller(
    payload: SellerProfileCreate,
    request: Request,
    user: CurrentUser = Depends(require_seller),
    service: UserService = Depends(get_user_service),
):
    return await service.create_seller(
        user.user_id, payload, getattr(request.state, "correlation_id", None)
    )


@router.get("/me/seller", response_model=SellerProfileResponse)
async def get_seller(
    response: Response,
    user: CurrentUser = Depends(require_seller),
    service: UserService = Depends(get_user_service),
):
    profile = await service.require_profile(user.user_id)
    if not profile.seller_profile:
        raise NotFoundError("Seller profile does not exist")
    response.headers["ETag"] = f'"{profile.seller_profile.version}"'
    return profile.seller_profile


@router.patch("/me/seller", response_model=SellerProfileResponse)
async def update_seller(
    payload: SellerProfileUpdate,
    response: Response,
    version: int = Depends(parse_if_match),
    user: CurrentUser = Depends(require_seller),
    service: UserService = Depends(get_user_service),
):
    seller = await service.update_seller(user.user_id, payload, version)
    response.headers["ETag"] = f'"{seller.version}"'
    return seller


@router.get("/sellers/{seller_id}", response_model=PublicSellerProfile)
async def public_seller(seller_id: UUID, service: UserService = Depends(get_user_service)):
    seller = await service.repo.public_seller(seller_id)
    if not seller:
        raise NotFoundError("Seller profile does not exist")
    return seller
