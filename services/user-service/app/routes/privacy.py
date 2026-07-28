from uuid import UUID

from fastapi import APIRouter, Depends, Security, status

from app.dependencies import CurrentUser, get_current_user, require_idempotency_key
from app.exceptions import NotFoundError
from app.routes.dependencies import get_user_service
from app.schemas import BuyerProfileResponse, PrivacyRequestCreate, PrivacyRequestResponse
from app.services import UserService

router = APIRouter(prefix="/me", tags=["lifecycle and privacy"])


@router.post("/deactivation", response_model=BuyerProfileResponse)
async def deactivate(
    _key: str = Depends(require_idempotency_key),
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.deactivate(user.user_id)


@router.post("/reactivation", response_model=BuyerProfileResponse)
async def reactivate(
    _key: str = Depends(require_idempotency_key),
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.reactivate(user.user_id)


@router.post(
    "/privacy-requests",
    response_model=PrivacyRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_privacy_request(
    payload: PrivacyRequestCreate,
    key: str = Depends(require_idempotency_key),
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.create_privacy_request(user.user_id, payload, key)


@router.get("/privacy-requests/{request_id}", response_model=PrivacyRequestResponse)
async def get_privacy_request(
    request_id: UUID,
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    profile = await service.require_profile(user.user_id)
    record = await service.repo.privacy_request(profile.id, request_id)
    if not record:
        raise NotFoundError("Privacy request does not exist")
    return record
