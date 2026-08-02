from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.clients import InventoryClient, ProductClient
from app.config import Settings
from app.dependencies.auth import Principal
from app.exceptions import ServiceError
from app.models.cart import Cart, CartItem, CartStatus, SavedItem
from app.models.reliability import AuditLog, IdempotencyRecord, OutboxEvent
from app.repositories import CartRepository
from app.schemas.cart import (
    AvailabilityLine,
    CartItemCreate,
    CheckoutReadinessResponse,
    ProductSnapshot,
)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class CartService:
    def __init__(
        self,
        repo: CartRepository,
        settings: Settings,
        products: ProductClient,
        inventory: InventoryClient,
    ) -> None:
        self.repo = repo
        self.session = repo.session
        self.settings = settings
        self.products = products
        self.inventory = inventory

    def _expires_at(self, guest: bool) -> datetime:
        days = (
            self.settings.guest_cart_ttl_days if guest else self.settings.cart_ttl_days
        )
        return datetime.now(UTC) + timedelta(days=days)

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ServiceError(
                409, "concurrent_cart_change", "Cart changed concurrently"
            ) from exc

    def _assert_active(self, cart: Cart) -> None:
        if cart.status != CartStatus.ACTIVE:
            raise ServiceError(409, "cart_not_active", "Cart is not active")
        expires_at = cart.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise ServiceError(410, "cart_expired", "Cart has expired")

    def _assert_version(self, cart: Cart, expected_version: int) -> None:
        if cart.version != expected_version:
            message = (
                f"Expected cart version {expected_version}; "
                f"current version is {cart.version}"
            )
            raise ServiceError(
                409,
                "version_conflict",
                message,
            )

    def _actor_key(self, principal: Principal | None, guest_token: str | None) -> str:
        if principal:
            return f"customer:{principal.subject}"
        if guest_token:
            return f"guest:{token_hash(guest_token)}"
        raise ServiceError(
            401, "cart_identity_required", "Sign in or provide X-Cart-Token"
        )

    async def create_guest_cart(self, request_id: str | None) -> tuple[str, Cart]:
        raw_token = secrets.token_urlsafe(32)
        cart = Cart(
            guest_token_hash=token_hash(raw_token),
            status=CartStatus.ACTIVE,
            expires_at=self._expires_at(True),
            items=[],
            saved_items=[],
        )
        self.session.add(cart)
        await self.session.flush()
        self._record(cart, None, "cart.created", request_id)
        await self._commit()
        return raw_token, cart

    async def resolve_cart(
        self,
        principal: Principal | None,
        guest_token: str | None,
        *,
        create_customer: bool = True,
        for_update: bool = False,
    ) -> Cart:
        created = False
        if principal:
            cart = await self.repo.get_active_customer_cart(
                principal.subject, for_update=for_update
            )
            if not cart and create_customer:
                cart = Cart(
                    customer_id=principal.subject,
                    status=CartStatus.ACTIVE,
                    expires_at=self._expires_at(False),
                    items=[],
                    saved_items=[],
                )
                self.session.add(cart)
                await self.session.flush()
                created = True
            if not cart:
                raise ServiceError(404, "cart_not_found", "Active cart was not found")
        elif guest_token:
            cart = await self.repo.get_guest_cart(
                token_hash(guest_token), for_update=for_update
            )
            if not cart:
                raise ServiceError(
                    404, "guest_cart_not_found", "Guest cart was not found"
                )
        else:
            raise ServiceError(
                401, "cart_identity_required", "Sign in or provide X-Cart-Token"
            )
        self._assert_active(cart)
        if created and not for_update:
            await self._commit()
        return cart

    def _record(
        self,
        cart: Cart,
        actor_id: UUID | None,
        event_type: str,
        request_id: str | None,
        *,
        resource_id: UUID | None = None,
    ) -> None:
        target_id = resource_id or cart.id
        self.session.add(
            AuditLog(
                actor_id=actor_id,
                action=event_type,
                resource_type="cart",
                resource_id=target_id,
                before_data=None,
                after_data={"cart_id": str(cart.id), "version": cart.version},
                request_id=request_id,
            )
        )
        self.session.add(
            OutboxEvent(
                aggregate_type="cart",
                aggregate_id=cart.id,
                event_type=event_type,
                payload={
                    "cart_id": str(cart.id),
                    "customer_id": str(cart.customer_id) if cart.customer_id else None,
                    "version": cart.version,
                    "request_id": request_id,
                },
            )
        )

    async def add_item(
        self,
        data: CartItemCreate,
        principal: Principal | None,
        guest_token: str | None,
        expected_version: int,
        idempotency_key: str | None,
        request_id: str | None,
    ) -> Cart:
        actor_key = self._actor_key(principal, guest_token)
        body_hash = hashlib.sha256(data.model_dump_json().encode()).hexdigest()
        if idempotency_key:
            previous = await self.repo.get_idempotency(actor_key, idempotency_key)
            if previous:
                if previous.request_hash != body_hash:
                    raise ServiceError(
                        409, "idempotency_conflict", "Key was used for another request"
                    )
                cart = (
                    await self.repo.get(previous.resource_id)
                    if previous.resource_id
                    else None
                )
                if cart:
                    return cart

        cart = await self.resolve_cart(
            principal, guest_token, create_customer=True, for_update=True
        )
        self._assert_version(cart, expected_version)
        if data.quantity > self.settings.max_item_quantity:
            raise ServiceError(
                422, "quantity_limit", "Item quantity exceeds the cart limit"
            )
        snapshot = await self.products.get_snapshot(
            data.product_id, data.variant_id, request_id
        )
        existing = next(
            (item for item in cart.items if item.variant_id == data.variant_id), None
        )
        if existing:
            new_quantity = existing.quantity + data.quantity
            if new_quantity > self.settings.max_item_quantity:
                raise ServiceError(
                    422, "quantity_limit", "Item quantity exceeds the cart limit"
                )
            existing.quantity = new_quantity
            existing.version += 1
            self._apply_snapshot(existing, snapshot)
        else:
            if len(cart.items) >= self.settings.max_distinct_items:
                raise ServiceError(
                    422, "cart_item_limit", "Cart has too many distinct items"
                )
            if cart.items and cart.currency_code != snapshot.currency_code:
                raise ServiceError(
                    422, "currency_mismatch", "Cart cannot mix currencies"
                )
            cart.currency_code = snapshot.currency_code
            item = CartItem(
                cart_id=cart.id,
                quantity=data.quantity,
                **snapshot.model_dump(),
            )
            cart.items.append(item)
        cart.version += 1
        cart.expires_at = self._expires_at(principal is None)
        self._record(
            cart,
            principal.subject if principal else None,
            "cart.item_added",
            request_id,
        )
        if idempotency_key:
            self.session.add(
                IdempotencyRecord(
                    actor_key=actor_key,
                    idempotency_key=idempotency_key,
                    request_hash=body_hash,
                    resource_id=cart.id,
                    response_body=json.dumps({"cart_id": str(cart.id)}),
                )
            )
        await self._commit()
        return await self.repo.get(cart.id) or cart

    @staticmethod
    def _apply_snapshot(item: CartItem, snapshot: ProductSnapshot) -> None:
        for field, value in snapshot.model_dump().items():
            setattr(item, field, value)

    async def update_quantity(
        self,
        item_id: UUID,
        quantity: int,
        principal: Principal | None,
        guest_token: str | None,
        expected_version: int,
        request_id: str | None,
    ) -> Cart:
        cart = await self.resolve_cart(principal, guest_token, for_update=True)
        self._assert_version(cart, expected_version)
        if quantity > self.settings.max_item_quantity:
            raise ServiceError(
                422, "quantity_limit", "Item quantity exceeds the cart limit"
            )
        item = next((value for value in cart.items if value.id == item_id), None)
        if not item:
            raise ServiceError(404, "cart_item_not_found", "Cart item was not found")
        item.quantity = quantity
        item.version += 1
        cart.version += 1
        self._record(
            cart,
            principal.subject if principal else None,
            "cart.item_updated",
            request_id,
            resource_id=item.id,
        )
        await self._commit()
        return await self.repo.get(cart.id) or cart

    async def remove_item(
        self,
        item_id: UUID,
        principal: Principal | None,
        guest_token: str | None,
        expected_version: int,
        request_id: str | None,
    ) -> Cart:
        cart = await self.resolve_cart(principal, guest_token, for_update=True)
        self._assert_version(cart, expected_version)
        item = next((value for value in cart.items if value.id == item_id), None)
        if not item:
            raise ServiceError(404, "cart_item_not_found", "Cart item was not found")
        cart.items.remove(item)
        await self.session.delete(item)
        cart.version += 1
        self._record(
            cart,
            principal.subject if principal else None,
            "cart.item_removed",
            request_id,
            resource_id=item_id,
        )
        await self._commit()
        return await self.repo.get(cart.id) or cart

    async def save_for_later(
        self,
        item_id: UUID,
        principal: Principal | None,
        guest_token: str | None,
        expected_version: int,
        request_id: str | None,
    ) -> Cart:
        cart = await self.resolve_cart(principal, guest_token, for_update=True)
        self._assert_version(cart, expected_version)
        item = next((value for value in cart.items if value.id == item_id), None)
        if not item:
            raise ServiceError(404, "cart_item_not_found", "Cart item was not found")
        if not any(value.variant_id == item.variant_id for value in cart.saved_items):
            cart.saved_items.append(
                SavedItem(
                    cart_id=cart.id,
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    sku=item.sku,
                    product_name=item.product_name,
                    variant_name=item.variant_name,
                    image_url=item.image_url,
                    unit_price=item.unit_price,
                    currency_code=item.currency_code,
                )
            )
        cart.items.remove(item)
        await self.session.delete(item)
        cart.version += 1
        self._record(
            cart,
            principal.subject if principal else None,
            "cart.item_saved",
            request_id,
        )
        await self._commit()
        return await self.repo.get(cart.id) or cart

    async def move_saved_to_cart(
        self,
        saved_item_id: UUID,
        principal: Principal | None,
        guest_token: str | None,
        expected_version: int,
        request_id: str | None,
    ) -> Cart:
        cart = await self.resolve_cart(principal, guest_token, for_update=True)
        self._assert_version(cart, expected_version)
        saved = next(
            (value for value in cart.saved_items if value.id == saved_item_id), None
        )
        if not saved:
            raise ServiceError(404, "saved_item_not_found", "Saved item was not found")
        snapshot = await self.products.get_snapshot(
            saved.product_id, saved.variant_id, request_id
        )
        existing = next(
            (value for value in cart.items if value.variant_id == saved.variant_id),
            None,
        )
        if existing:
            if existing.quantity >= self.settings.max_item_quantity:
                raise ServiceError(
                    422, "quantity_limit", "Item quantity exceeds the cart limit"
                )
            existing.quantity += 1
            existing.version += 1
            self._apply_snapshot(existing, snapshot)
        else:
            cart.items.append(
                CartItem(cart_id=cart.id, quantity=1, **snapshot.model_dump())
            )
        cart.saved_items.remove(saved)
        await self.session.delete(saved)
        cart.version += 1
        self._record(
            cart,
            principal.subject if principal else None,
            "cart.saved_item_moved",
            request_id,
        )
        await self._commit()
        return await self.repo.get(cart.id) or cart

    async def delete_saved(
        self,
        saved_item_id: UUID,
        principal: Principal | None,
        guest_token: str | None,
        expected_version: int,
        request_id: str | None,
    ) -> Cart:
        cart = await self.resolve_cart(principal, guest_token, for_update=True)
        self._assert_version(cart, expected_version)
        saved = next(
            (value for value in cart.saved_items if value.id == saved_item_id), None
        )
        if not saved:
            raise ServiceError(404, "saved_item_not_found", "Saved item was not found")
        cart.saved_items.remove(saved)
        await self.session.delete(saved)
        cart.version += 1
        self._record(
            cart,
            principal.subject if principal else None,
            "cart.saved_item_removed",
            request_id,
        )
        await self._commit()
        return await self.repo.get(cart.id) or cart

    async def readiness(
        self,
        principal: Principal | None,
        guest_token: str | None,
        expected_version: int,
        request_id: str | None,
    ) -> CheckoutReadinessResponse:
        cart = await self.resolve_cart(principal, guest_token, for_update=True)
        self._assert_version(cart, expected_version)
        lines: list[AvailabilityLine] = []
        price_changed = False
        for item in cart.items:
            snapshot = await self.products.get_snapshot(
                item.product_id, item.variant_id, request_id
            )
            if (
                item.unit_price != snapshot.unit_price
                or item.product_version != snapshot.product_version
            ):
                price_changed = True
                self._apply_snapshot(item, snapshot)
                item.version += 1
            available, is_available = await self.inventory.availability(
                item.sku, item.quantity, request_id
            )
            lines.append(
                AvailabilityLine(
                    item_id=item.id,
                    sku=item.sku,
                    requested_quantity=item.quantity,
                    available_quantity=available,
                    is_available=is_available,
                )
            )
        if price_changed:
            cart.version += 1
            self._record(
                cart,
                principal.subject if principal else None,
                "cart.prices_refreshed",
                request_id,
            )
            await self._commit()
        subtotal = sum(
            (item.unit_price * item.quantity for item in cart.items), Decimal("0.00")
        )
        unavailable = [line for line in lines if not line.is_available]
        return CheckoutReadinessResponse(
            cart_id=cart.id,
            ready=bool(cart.items) and not unavailable,
            price_changed=price_changed,
            unavailable_items=unavailable,
            items=lines,
            subtotal=subtotal,
            currency_code=cart.currency_code,
        )

    async def merge_guest(
        self,
        principal: Principal,
        guest_token: str,
        request_id: str | None,
    ) -> Cart:
        guest = await self.repo.get_guest_cart(token_hash(guest_token), for_update=True)
        if not guest:
            raise ServiceError(404, "guest_cart_not_found", "Guest cart was not found")
        customer = await self.resolve_cart(
            principal, None, create_customer=True, for_update=True
        )
        for source in list(guest.items):
            target = next(
                (
                    value
                    for value in customer.items
                    if value.variant_id == source.variant_id
                ),
                None,
            )
            if target:
                merged_quantity = target.quantity + source.quantity
                if merged_quantity > self.settings.max_item_quantity:
                    raise ServiceError(
                        422,
                        "quantity_limit",
                        f"Merged quantity for {source.sku} exceeds the limit",
                    )
                target.quantity = merged_quantity
                target.version += 1
            else:
                customer.items.append(
                    CartItem(
                        cart_id=customer.id,
                        product_id=source.product_id,
                        variant_id=source.variant_id,
                        sku=source.sku,
                        product_name=source.product_name,
                        variant_name=source.variant_name,
                        image_url=source.image_url,
                        quantity=source.quantity,
                        unit_price=source.unit_price,
                        currency_code=source.currency_code,
                        product_version=source.product_version,
                    )
                )
        existing_saved = {value.variant_id for value in customer.saved_items}
        for source in guest.saved_items:
            if source.variant_id not in existing_saved:
                customer.saved_items.append(
                    SavedItem(
                        cart_id=customer.id,
                        product_id=source.product_id,
                        variant_id=source.variant_id,
                        sku=source.sku,
                        product_name=source.product_name,
                        variant_name=source.variant_name,
                        image_url=source.image_url,
                        unit_price=source.unit_price,
                        currency_code=source.currency_code,
                    )
                )
        guest.status = CartStatus.MERGED
        guest.merged_into_cart_id = customer.id
        guest.guest_token_hash = None
        guest.version += 1
        customer.version += 1
        customer.expires_at = self._expires_at(False)
        self._record(customer, principal.subject, "cart.guest_merged", request_id)
        await self._commit()
        return await self.repo.get(customer.id) or customer

    async def clear(
        self,
        principal: Principal | None,
        guest_token: str | None,
        expected_version: int,
        request_id: str | None,
    ) -> Cart:
        cart = await self.resolve_cart(principal, guest_token, for_update=True)
        self._assert_version(cart, expected_version)
        for item in list(cart.items):
            await self.session.delete(item)
        cart.items.clear()
        cart.version += 1
        self._record(
            cart, principal.subject if principal else None, "cart.cleared", request_id
        )
        await self._commit()
        return await self.repo.get(cart.id) or cart

    async def mark_checked_out(
        self, cart_id: UUID, customer_id: UUID, order_id: UUID, request_id: str | None
    ) -> Cart:
        cart = await self.repo.get(cart_id, for_update=True)
        if not cart or cart.customer_id != customer_id:
            raise ServiceError(404, "cart_not_found", "Customer cart was not found")
        self._assert_active(cart)
        if not cart.items:
            raise ServiceError(409, "empty_cart", "Empty cart cannot be checked out")
        cart.status = CartStatus.CHECKED_OUT
        cart.version += 1
        self._record(cart, customer_id, "cart.checked_out", request_id)
        self.session.add(
            OutboxEvent(
                aggregate_type="cart",
                aggregate_id=cart.id,
                event_type="cart.checkout_linked",
                payload={
                    "cart_id": str(cart.id),
                    "customer_id": str(customer_id),
                    "order_id": str(order_id),
                    "request_id": request_id,
                },
            )
        )
        await self._commit()
        return cart
