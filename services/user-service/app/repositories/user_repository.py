from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Address,
    AddressType,
    BuyerProfile,
    NotificationPreference,
    PrivacyRequest,
    SellerProfile,
    UserConsent,
    UserPreference,
)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def profile_by_user_id(self, user_id: UUID) -> BuyerProfile | None:
        result = await self.session.execute(
            select(BuyerProfile)
            .where(BuyerProfile.user_id == user_id)
            .options(selectinload(BuyerProfile.seller_profile))
        )
        return result.scalar_one_or_none()

    async def public_seller(self, seller_id: UUID) -> SellerProfile | None:
        return await self.session.get(SellerProfile, seller_id)

    async def addresses(
        self, profile_id: UUID, address_type: AddressType | None = None
    ) -> list[Address]:
        query = select(Address).where(
            Address.buyer_profile_id == profile_id, Address.deleted_at.is_(None)
        )
        if address_type:
            query = query.where(Address.address_type == address_type)
        result = await self.session.execute(query.order_by(Address.created_at.desc()))
        return list(result.scalars())

    async def address(self, profile_id: UUID, address_id: UUID) -> Address | None:
        result = await self.session.execute(
            select(Address).where(
                Address.id == address_id,
                Address.buyer_profile_id == profile_id,
                Address.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def clear_default(
        self, profile_id: UUID, address_type: AddressType, except_id: UUID | None = None
    ) -> None:
        query = (
            update(Address)
            .where(
                Address.buyer_profile_id == profile_id,
                Address.address_type == address_type,
                Address.is_default.is_(True),
                Address.deleted_at.is_(None),
            )
            .values(is_default=False, version=Address.version + 1)
        )
        if except_id:
            query = query.where(Address.id != except_id)
        await self.session.execute(query)

    async def preference(self, profile_id: UUID) -> UserPreference | None:
        result = await self.session.execute(
            select(UserPreference).where(UserPreference.buyer_profile_id == profile_id)
        )
        return result.scalar_one_or_none()

    async def notification_preferences(self, profile_id: UUID) -> list[NotificationPreference]:
        result = await self.session.execute(
            select(NotificationPreference).where(
                NotificationPreference.buyer_profile_id == profile_id
            )
        )
        return list(result.scalars())

    async def consents(self, profile_id: UUID) -> list[UserConsent]:
        result = await self.session.execute(
            select(UserConsent).where(UserConsent.buyer_profile_id == profile_id)
        )
        return list(result.scalars())

    async def privacy_request(self, profile_id: UUID, request_id: UUID) -> PrivacyRequest | None:
        result = await self.session.execute(
            select(PrivacyRequest).where(
                PrivacyRequest.id == request_id,
                PrivacyRequest.buyer_profile_id == profile_id,
            )
        )
        return result.scalar_one_or_none()
