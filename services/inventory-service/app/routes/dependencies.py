from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.inventory_service import InventoryService


async def get_inventory_service(
    session: AsyncSession = Depends(get_session),
) -> InventoryService:
    return InventoryService(session)
