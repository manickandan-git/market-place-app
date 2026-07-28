from fastapi import APIRouter, Depends, Response, Security

from app.dependencies import CurrentUser, get_current_user, parse_if_match
from app.exceptions import NotFoundError
from app.models.consent import ConsentSource
from app.routes.dependencies import get_user_service
from app.schemas import (
    ConsentResponse,
    ConsentsUpdate,
    NotificationPreferenceResponse,
    NotificationPreferencesUpdate,
    UserPreferenceResponse,
    UserPreferenceUpdate,
)
from app.services import UserService

router = APIRouter(prefix="/me", tags=["preferences"])


@router.get("/preferences", response_model=UserPreferenceResponse)
async def get_preferences(
    response: Response,
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    profile = await service.require_profile(user.user_id)
    preference = await service.repo.preference(profile.id)
    if not preference:
        raise NotFoundError("Preferences do not exist")
    response.headers["ETag"] = f'"{preference.version}"'
    return preference


@router.patch("/preferences", response_model=UserPreferenceResponse)
async def update_preferences(
    payload: UserPreferenceUpdate,
    response: Response,
    version: int = Depends(parse_if_match),
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    preference = await service.update_preferences(user.user_id, payload, version)
    response.headers["ETag"] = f'"{preference.version}"'
    return preference


@router.get("/notification-preferences", response_model=list[NotificationPreferenceResponse])
async def get_notifications(
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    profile = await service.require_profile(user.user_id)
    return await service.repo.notification_preferences(profile.id)


@router.put("/notification-preferences", response_model=list[NotificationPreferenceResponse])
async def update_notifications(
    payload: NotificationPreferencesUpdate,
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.upsert_notifications(user.user_id, payload)


@router.get("/consents", response_model=list[ConsentResponse])
async def get_consents(
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    profile = await service.require_profile(user.user_id)
    return await service.repo.consents(profile.id)


@router.put("/consents", response_model=list[ConsentResponse])
async def update_consents(
    payload: ConsentsUpdate,
    user: CurrentUser = Security(get_current_user),
    service: UserService = Depends(get_user_service),
):
    return await service.upsert_consents(user.user_id, payload, ConsentSource.WEB)
