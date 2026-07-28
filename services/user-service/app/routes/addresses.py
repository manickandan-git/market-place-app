from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, Security, status

from app.dependencies import (
    CurrentUser,
    get_current_user,
    parse_if_match,
    require_idempotency_key,
)
from app.exceptions import NotFoundError
from app.models.address import AddressType
from app.routes.dependencies import get_user_service
from app.schemas import AddressCreate, AddressResponse, AddressUpdate, MessageResponse
from app.services import UserService

router = APIRouter(prefix="/me/addresses", tags=["addresses"])


@router.get("", response_model=list[AddressResponse])
async def list_addresses(
    address_type: AddressType | None = None,
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    profile = await service.require_profile(user.user_id)
    return await service.repo.addresses(profile.id, address_type)


@router.post("", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def create_address(
    payload: AddressCreate,
    request: Request,
    key: str = Depends(require_idempotency_key),
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.create_address(
        user.user_id, payload, key, getattr(request.state, "correlation_id", None)
    )


@router.get("/{address_id}", response_model=AddressResponse)
async def get_address(
    address_id: UUID,
    response: Response,
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    profile = await service.require_profile(user.user_id)
    address = await service.repo.address(profile.id, address_id)
    if not address:
        raise NotFoundError("Address does not exist")
    response.headers["ETag"] = f'"{address.version}"'
    return address


@router.patch("/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: UUID,
    payload: AddressUpdate,
    response: Response,
    version: int = Depends(parse_if_match),
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    address = await service.update_address(user.user_id, address_id, payload, version)
    response.headers["ETag"] = f'"{address.version}"'
    return address


@router.delete("/{address_id}", response_model=MessageResponse)
async def delete_address(
    address_id: UUID,
    version: int = Depends(parse_if_match),
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    await service.delete_address(user.user_id, address_id, version)
    return MessageResponse(message="Address deleted")
