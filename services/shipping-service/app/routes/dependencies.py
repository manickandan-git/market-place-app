from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session
from app.services.auth_client import AuthClient
from app.services.order_client import OrderClient
from app.services.shipment_service import ShipmentService


@lru_cache
def get_auth_client() -> AuthClient:
    # Must be a singleton: its whole purpose is caching the service token
    # across requests instead of re-authenticating on every call.
    return AuthClient(get_settings())


async def get_shipment_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    auth_client: AuthClient = Depends(get_auth_client),
) -> ShipmentService:
    return ShipmentService(
        session,
        settings,
        OrderClient(settings),
        auth_client,
    )
