import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.exceptions import ConflictError, NotFoundError, StaleVersionError
from app.models import (
    Address,
    AuditLog,
    BuyerProfile,
    ConsentSource,
    IdempotencyRecord,
    NotificationPreference,
    OutboxEvent,
    PrivacyRequest,
    PrivacyRequestStatus,
    ProfileStatus,
    SellerProfile,
    UserConsent,
    UserPreference,
)
from app.repositories import UserRepository
from app.schemas import (
    AddressCreate,
    AddressResponse,
    AddressUpdate,
    BuyerProfileCreate,
    BuyerProfileUpdate,
    ConsentsUpdate,
    NotificationPreferencesUpdate,
    PrivacyRequestCreate,
    SellerProfileCreate,
    SellerProfileUpdate,
    UserPreferenceUpdate,
)


def _jsonable(data: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(data, default=str))


class UserService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.repo = UserRepository(session)

    async def require_profile(self, user_id: UUID) -> BuyerProfile:
        profile = await self.repo.profile_by_user_id(user_id)
        if profile is None:
            raise NotFoundError("Buyer profile does not exist")
        return profile

    async def create_profile(
        self, user_id: UUID, payload: BuyerProfileCreate, correlation_id: str | None
    ) -> BuyerProfile:
        if await self.repo.profile_by_user_id(user_id):
            raise ConflictError("Buyer profile already exists")
        profile = BuyerProfile(
            user_id=user_id,
            **payload.model_dump(),
            is_profile_complete=bool(payload.first_name and payload.last_name),
        )
        self.session.add(profile)
        await self.session.flush()
        self.session.add(UserPreference(buyer_profile_id=profile.id))
        self._audit(
            user_id, "profile.created", "buyer_profile", profile.id, None, payload.model_dump()
        )
        self._event(profile.id, "user.profile.created.v1", {"user_id": str(user_id)})
        await self.session.commit()
        return await self.require_profile(user_id)

    async def update_profile(
        self,
        user_id: UUID,
        payload: BuyerProfileUpdate,
        version: int,
        correlation_id: str | None,
    ) -> BuyerProfile:
        profile = await self.require_profile(user_id)
        self._check_version(profile.version, version)
        before = {key: getattr(profile, key) for key in payload.model_fields_set}
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(profile, key, value)
        profile.is_profile_complete = bool(profile.first_name and profile.last_name)
        profile.version += 1
        self._audit(
            user_id,
            "profile.updated",
            "buyer_profile",
            profile.id,
            before,
            payload.model_dump(exclude_unset=True),
            correlation_id,
        )
        self._event(
            profile.id, "user.profile.updated.v1", {"changed": sorted(payload.model_fields_set)}
        )
        await self.session.commit()
        return await self.require_profile(user_id)

    async def create_seller(
        self, user_id: UUID, payload: SellerProfileCreate, correlation_id: str | None
    ) -> SellerProfile:
        profile = await self.require_profile(user_id)
        if profile.seller_profile:
            raise ConflictError("Seller profile already exists")
        seller = SellerProfile(buyer_profile_id=profile.id, **payload.model_dump(mode="json"))
        self.session.add(seller)
        await self.session.flush()
        self._audit(
            user_id, "seller.created", "seller_profile", seller.id, None, payload.model_dump()
        )
        self._event(seller.id, "user.seller_profile.created.v1", {"user_id": str(user_id)})
        await self.session.commit()
        await self.session.refresh(seller)
        return seller

    async def update_seller(
        self, user_id: UUID, payload: SellerProfileUpdate, version: int
    ) -> SellerProfile:
        profile = await self.require_profile(user_id)
        seller = profile.seller_profile
        if not seller:
            raise NotFoundError("Seller profile does not exist")
        self._check_version(seller.version, version)
        before = {key: getattr(seller, key) for key in payload.model_fields_set}
        for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
            setattr(seller, key, value)
        seller.version += 1
        self._audit(
            user_id,
            "seller.updated",
            "seller_profile",
            seller.id,
            before,
            payload.model_dump(exclude_unset=True),
        )
        self._event(seller.id, "user.seller_profile.updated.v1", {"user_id": str(user_id)})
        await self.session.commit()
        await self.session.refresh(seller)
        return seller

    async def create_address(
        self, user_id: UUID, payload: AddressCreate, key: str, correlation_id: str | None
    ) -> Address:
        profile = await self.require_profile(user_id)
        request_data = payload.model_dump(mode="json")
        cached = await self._idempotent_response(user_id, "address.create", key, request_data)
        if cached:
            existing = await self.repo.address(profile.id, UUID(cached["id"]))
            if existing:
                return existing
        if payload.is_default:
            await self.repo.clear_default(profile.id, payload.address_type)
        address = Address(buyer_profile_id=profile.id, **request_data)
        self.session.add(address)
        await self.session.flush()
        self._audit(user_id, "address.created", "address", address.id, None, request_data)
        self._event(
            address.id,
            "user.address.created.v1",
            {"user_id": str(user_id), "address_type": payload.address_type.value},
        )
        response = AddressResponse.model_validate(address).model_dump(mode="json")
        self._store_idempotency(user_id, "address.create", key, request_data, 201, response)
        await self.session.commit()
        await self.session.refresh(address)
        return address

    async def update_address(
        self, user_id: UUID, address_id: UUID, payload: AddressUpdate, version: int
    ) -> Address:
        profile = await self.require_profile(user_id)
        address = await self.repo.address(profile.id, address_id)
        if not address:
            raise NotFoundError("Address does not exist")
        self._check_version(address.version, version)
        values = payload.model_dump(exclude_unset=True)
        target_type = values.get("address_type", address.address_type)
        if values.get("is_default"):
            await self.repo.clear_default(profile.id, target_type, address.id)
        before = {key: getattr(address, key) for key in payload.model_fields_set}
        for key, value in values.items():
            setattr(address, key, value)
        address.version += 1
        self._audit(user_id, "address.updated", "address", address.id, before, values)
        self._event(address.id, "user.address.updated.v1", {"user_id": str(user_id)})
        await self.session.commit()
        await self.session.refresh(address)
        return address

    async def delete_address(self, user_id: UUID, address_id: UUID, version: int) -> None:
        profile = await self.require_profile(user_id)
        address = await self.repo.address(profile.id, address_id)
        if not address:
            raise NotFoundError("Address does not exist")
        self._check_version(address.version, version)
        address.deleted_at = datetime.now(UTC)
        address.is_default = False
        address.version += 1
        self._audit(user_id, "address.deleted", "address", address.id, None, None)
        self._event(address.id, "user.address.deleted.v1", {"user_id": str(user_id)})
        await self.session.commit()

    async def update_preferences(
        self, user_id: UUID, payload: UserPreferenceUpdate, version: int
    ) -> UserPreference:
        profile = await self.require_profile(user_id)
        preference = await self.repo.preference(profile.id)
        if not preference:
            preference = UserPreference(buyer_profile_id=profile.id)
            self.session.add(preference)
            await self.session.flush()
        self._check_version(preference.version, version)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(preference, key, value)
        preference.version += 1
        self._audit(
            user_id,
            "preferences.updated",
            "user_preference",
            preference.id,
            None,
            payload.model_dump(exclude_unset=True),
        )
        self._event(preference.id, "user.preferences.updated.v1", {"user_id": str(user_id)})
        await self.session.commit()
        await self.session.refresh(preference)
        return preference

    async def upsert_notifications(
        self, user_id: UUID, payload: NotificationPreferencesUpdate
    ) -> list[NotificationPreference]:
        profile = await self.require_profile(user_id)
        existing = {
            (item.channel, item.category): item
            for item in await self.repo.notification_preferences(profile.id)
        }
        for item in payload.preferences:
            record = existing.get((item.channel, item.category))
            if record:
                record.is_enabled = item.is_enabled
                record.version += 1
            else:
                self.session.add(
                    NotificationPreference(buyer_profile_id=profile.id, **item.model_dump())
                )
        self._audit(user_id, "notifications.updated", "buyer_profile", profile.id, None, None)
        await self.session.commit()
        return await self.repo.notification_preferences(profile.id)

    async def upsert_consents(
        self, user_id: UUID, payload: ConsentsUpdate, source: ConsentSource
    ) -> list[UserConsent]:
        profile = await self.require_profile(user_id)
        existing = {item.consent_type: item for item in await self.repo.consents(profile.id)}
        for item in payload.consents:
            record = existing.get(item.consent_type)
            if record:
                for key, value in item.model_dump().items():
                    setattr(record, key, value)
                record.source = source
                record.decided_at = datetime.now(UTC)
                record.version += 1
            else:
                self.session.add(
                    UserConsent(buyer_profile_id=profile.id, source=source, **item.model_dump())
                )
        self._audit(user_id, "consents.updated", "buyer_profile", profile.id, None, None)
        await self.session.commit()
        return await self.repo.consents(profile.id)

    async def create_privacy_request(
        self, user_id: UUID, payload: PrivacyRequestCreate, key: str
    ) -> PrivacyRequest:
        profile = await self.require_profile(user_id)
        data = payload.model_dump(mode="json")
        cached = await self._idempotent_response(user_id, "privacy.create", key, data)
        if cached:
            record = await self.repo.privacy_request(profile.id, UUID(cached["id"]))
            if record:
                return record
        record = PrivacyRequest(
            buyer_profile_id=profile.id,
            **data,
            status=PrivacyRequestStatus.PENDING,
            due_at=datetime.now(UTC) + timedelta(days=30),
        )
        self.session.add(record)
        if payload.request_type.value == "deletion":
            profile.status = ProfileStatus.DELETION_PENDING
            profile.version += 1
        await self.session.flush()
        self._audit(user_id, "privacy.requested", "privacy_request", record.id, None, data)
        self._event(
            record.id,
            "user.privacy_requested.v1",
            {"user_id": str(user_id), "request_type": payload.request_type.value},
        )
        response = {"id": str(record.id)}
        self._store_idempotency(user_id, "privacy.create", key, data, 202, response)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def deactivate(self, user_id: UUID) -> BuyerProfile:
        profile = await self.require_profile(user_id)
        if profile.status == ProfileStatus.DEACTIVATED:
            return profile
        profile.status = ProfileStatus.DEACTIVATED
        profile.deactivated_at = datetime.now(UTC)
        profile.version += 1
        self._audit(user_id, "profile.deactivated", "buyer_profile", profile.id, None, None)
        self._event(profile.id, "user.profile.deactivated.v1", {"user_id": str(user_id)})
        await self.session.commit()
        return profile

    async def reactivate(self, user_id: UUID) -> BuyerProfile:
        profile = await self.require_profile(user_id)
        if profile.status == ProfileStatus.DELETION_PENDING:
            raise ConflictError("Cancel the active deletion request before reactivation")
        profile.status = ProfileStatus.ACTIVE
        profile.deactivated_at = None
        profile.version += 1
        self._audit(user_id, "profile.reactivated", "buyer_profile", profile.id, None, None)
        self._event(profile.id, "user.profile.reactivated.v1", {"user_id": str(user_id)})
        await self.session.commit()
        return profile

    @staticmethod
    def _check_version(current: int, supplied: int) -> None:
        if current != supplied:
            raise StaleVersionError(f"Expected version {current}, received {supplied}")

    def _audit(
        self,
        user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        before: dict | None,
        after: dict | None,
        correlation_id: str | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=user_id,
                subject_user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before_values=_jsonable(before) if before else None,
                after_values=_jsonable(after) if after else None,
                correlation_id=correlation_id,
            )
        )

    def _event(self, aggregate_id: UUID, event_type: str, payload: dict) -> None:
        self.session.add(
            OutboxEvent(
                aggregate_type=event_type.split(".")[1],
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
            )
        )

    @staticmethod
    def _hash(data: dict) -> str:
        raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    async def _idempotent_response(
        self, user_id: UUID, operation: str, key: str, request: dict
    ) -> dict | None:
        result = await self.session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.idempotency_key == key,
                IdempotencyRecord.expires_at > datetime.now(UTC),
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return None
        if record.request_hash != self._hash(request):
            raise ConflictError("Idempotency-Key was already used with a different request")
        return record.response_body

    def _store_idempotency(
        self,
        user_id: UUID,
        operation: str,
        key: str,
        request: dict,
        status_code: int,
        response: dict,
    ) -> None:
        self.session.add(
            IdempotencyRecord(
                user_id=user_id,
                operation=operation,
                idempotency_key=key,
                request_hash=self._hash(request),
                status_code=status_code,
                response_body=response,
                expires_at=datetime.now(UTC) + timedelta(hours=self.settings.idempotency_ttl_hours),
            )
        )
