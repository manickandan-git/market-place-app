from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import InventoryClient, ProductClient
from app.config import Settings, get_settings
from app.database import get_session
from app.repositories import CartRepository
from app.services import CartService


async def get_cart_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CartService:
    return CartService(
        CartRepository(session),
        settings,
        ProductClient(settings),
        InventoryClient(settings),
    )
