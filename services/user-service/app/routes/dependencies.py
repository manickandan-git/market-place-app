from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session
from app.services import UserService


def get_user_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UserService:
    return UserService(session, settings)
