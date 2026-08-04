from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session
from app.services.auth_client import AuthClient
from app.services.order_client import OrderClient
from app.services.payment_service import PaymentService
from app.services.stripe_client import StripeClient


@lru_cache
def get_auth_client() -> AuthClient:
    # Must be a singleton: its whole purpose is caching the service token
    # across requests instead of re-authenticating on every webhook.
    return AuthClient(get_settings())


@lru_cache
def get_stripe_client() -> StripeClient:
    return StripeClient(get_settings())


async def get_payment_service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    stripe_client: StripeClient = Depends(get_stripe_client),
    auth_client: AuthClient = Depends(get_auth_client),
) -> PaymentService:
    return PaymentService(
        session,
        settings,
        stripe_client,
        OrderClient(settings),
        auth_client,
    )
