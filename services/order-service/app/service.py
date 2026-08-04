from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal
from app.auth_client import AuthClient
from app.clients import CartClient, InventoryClient, NotificationClient, ProductClient
from app.config import Settings
from app.exceptions import ServiceError
from app.models import (
    AuditRecord,
    IdempotencyRecord,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    OutboxEvent,
    PaymentStatus,
)
from app.repository import OrderRepository
from app.schemas import (
    BatchReservationLine,
    BatchReservationRequest,
    CancelOrder,
    FulfillmentUpdate,
    OrderCreate,
    PaymentAuthorized,
    PaymentFailed,
    PaymentRefunded,
)


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        cart: CartClient,
        products: ProductClient,
        inventory: InventoryClient,
        notifications: NotificationClient,
        auth_client: AuthClient | None = None,
    ):
        self.session = session
        self.settings = settings
        self.repo = OrderRepository(session)
        self.cart = cart
        self.products = products
        self.inventory = inventory
        self.notifications = notifications
        self.auth_client = auth_client

    async def create(
        self,
        data: OrderCreate,
        principal: Principal,
        access_token: str,
        idempotency_key: str,
        request_id: str | None,
    ) -> Order:
        request_hash = hashlib.sha256(
            json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        previous = await self.repo.idempotency(str(principal.subject), idempotency_key)
        if previous:
            if previous.request_hash != request_hash:
                raise ServiceError(
                    409, "idempotency_conflict", "Key was used for another request"
                )
            order = await self.repo.get(previous.resource_id)
            if order:
                return order

        if await self.repo.by_customer_cart(principal.subject, data.cart_id):
            raise ServiceError(
                409, "order_already_exists", "An order already exists for this cart"
            )

        cart = await self.cart.snapshot(
            data.cart_id, data.cart_version, access_token, request_id
        )
        if cart.customer_id != principal.subject or not cart.items:
            raise ServiceError(
                403, "cart_ownership_error", "Cart does not belong to buyer"
            )

        seller_cache: dict[UUID, UUID] = {}
        for item in cart.items:
            seller_cache[item.product_id] = await self.products.seller_for_product(
                item.product_id, request_id
            )

        order_id = uuid4()
        order_number = self._order_number(order_id)
        expires_at = datetime.now(UTC) + timedelta(
            minutes=self.settings.reservation_minutes
        )
        reservation = await self.inventory.reserve_batch(
            BatchReservationRequest(
                cart_reference=str(cart.id),
                order_reference=order_number,
                expires_at=expires_at,
                lines=[
                    BatchReservationLine(
                        sku=item.sku,
                        quantity=item.quantity,
                        seller_id=seller_cache[item.product_id],
                    )
                    for item in cart.items
                ],
            ),
            access_token,
            idempotency_key,
            request_id,
        )

        billing = data.billing_address or data.shipping_address
        order = Order(
            id=order_id,
            order_number=order_number,
            customer_id=principal.subject,
            cart_id=cart.id,
            status=OrderStatus.PENDING_PAYMENT,
            payment_status=PaymentStatus.PENDING,
            currency_code=cart.currency_code,
            subtotal=cart.subtotal,
            grand_total=cart.subtotal,
            shipping_address=data.shipping_address.model_dump(mode="json"),
            billing_address=billing.model_dump(mode="json"),
            reservation_group_id=reservation.reservation_group_id,
            items=[
                OrderItem(
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    seller_id=seller_cache[item.product_id],
                    sku=item.sku,
                    product_name=item.product_name,
                    variant_name=item.variant_name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.unit_price * item.quantity,
                    product_version=item.product_version,
                )
                for item in cart.items
            ],
        )
        self.session.add_all(
            [
                order,
                IdempotencyRecord(
                    actor_id=str(principal.subject),
                    key=idempotency_key,
                    request_hash=request_hash,
                    resource_id=order.id,
                ),
                OrderStatusHistory(
                    order_id=order.id,
                    from_status=None,
                    to_status=OrderStatus.PENDING_PAYMENT.value,
                    actor_id=str(principal.subject),
                    reason="checkout_started",
                ),
            ]
        )
        self._event(order, "order.created", request_id)
        self._audit(order, str(principal.subject), "order.create", request_id)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            # Defense-in-depth against the upfront by_customer_cart check
            # above: a concurrent request for the same cart can still race
            # past it and hit the DB constraint instead. Translate that
            # specific race into the same clean 409 rather than a 500;
            # anything else is a genuine persistence failure.
            await self.session.rollback()
            await self.inventory.release_group(
                reservation.reservation_group_id,
                "Order persistence failed",
                access_token,
                request_id,
            )
            orig_message = str(getattr(exc, "orig", exc))
            # Postgres/asyncpg names the constraint in the message; SQLite
            # (used in tests) only lists the columns instead — check both
            # so this is exercised the same way in tests as in production.
            if (
                "uq_order_customer_cart" in orig_message
                or "orders.customer_id, orders.cart_id" in orig_message
            ):
                raise ServiceError(
                    409, "order_already_exists", "An order already exists for this cart"
                ) from exc
            raise
        except Exception:
            await self.session.rollback()
            await self.inventory.release_group(
                reservation.reservation_group_id,
                "Order persistence failed",
                access_token,
                request_id,
            )
            raise
        await self.session.refresh(order)
        try:
            await self.cart.mark_checked_out(
                cart.id, order.id, await self._service_token(access_token), request_id
            )
        except ServiceError:
            # order.created remains in the outbox for a retrying integration worker.
            pass
        await self.notifications.order_event(
            order.customer_id, order.order_number, "order_created", request_id
        )
        return order

    async def customer_order(self, order_id: UUID, principal: Principal) -> Order:
        order = await self.repo.get(order_id)
        if not order:
            raise ServiceError(404, "order_not_found", "Order was not found")
        if order.customer_id != principal.subject and not principal.has_role("admin"):
            raise ServiceError(404, "order_not_found", "Order was not found")
        return order

    async def cancel(
        self,
        order_id: UUID,
        data: CancelOrder,
        principal: Principal,
        access_token: str,
        expected_version: int,
        request_id: str | None,
    ) -> Order:
        order = await self.customer_order(order_id, principal)
        if order.version != expected_version:
            raise ServiceError(409, "version_conflict", "Order has changed")
        if order.status not in {
            OrderStatus.PENDING_PAYMENT,
            OrderStatus.PAYMENT_AUTHORIZED,
            OrderStatus.CONFIRMED,
        }:
            raise ServiceError(
                409, "order_not_cancellable", "Order cannot be cancelled"
            )
        if order.reservation_group_id:
            await self.inventory.release_group(
                order.reservation_group_id, data.reason, access_token, request_id
            )
        await self._transition(
            order,
            OrderStatus.CANCELLED,
            str(principal.subject),
            data.reason,
            request_id,
        )
        order.cancellation_reason = data.reason
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def payment_authorized(
        self,
        order_id: UUID,
        data: PaymentAuthorized,
        principal: Principal,
        access_token: str,
        request_id: str | None,
    ) -> Order:
        order = await self._locked(order_id)
        if order.status == OrderStatus.CONFIRMED:
            return order
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise ServiceError(
                409, "invalid_order_state", "Order is not awaiting payment"
            )
        if (
            data.currency_code != order.currency_code
            or data.authorized_amount != order.grand_total
        ):
            raise ServiceError(
                422, "payment_amount_mismatch", "Payment amount does not match order"
            )
        if order.reservation_group_id:
            await self.inventory.commit_group(
                order.reservation_group_id,
                order.order_number,
                await self._service_token(access_token),
                request_id,
            )
        order.payment_status = PaymentStatus.AUTHORIZED
        order.payment_reference = data.payment_reference
        await self._transition(
            order,
            OrderStatus.CONFIRMED,
            str(principal.subject),
            "payment_authorized",
            request_id,
        )
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def payment_failed(
        self,
        order_id: UUID,
        data: PaymentFailed,
        principal: Principal,
        access_token: str,
        request_id: str | None,
    ) -> Order:
        order = await self._locked(order_id)
        if order.status == OrderStatus.PAYMENT_FAILED:
            return order
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise ServiceError(
                409, "invalid_order_state", "Order is not awaiting payment"
            )
        if order.reservation_group_id:
            await self.inventory.release_group(
                order.reservation_group_id,
                data.reason,
                await self._service_token(access_token),
                request_id,
            )
        order.payment_status = PaymentStatus.FAILED
        order.payment_reference = data.payment_reference
        await self._transition(
            order,
            OrderStatus.PAYMENT_FAILED,
            str(principal.subject),
            data.reason,
            request_id,
        )
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def payment_refunded(
        self,
        order_id: UUID,
        data: PaymentRefunded,
        principal: Principal,
        request_id: str | None,
    ) -> Order:
        """A refund never changes Order.status (fulfillment keeps running
        independently of a post-hoc refund) or the Inventory reservation
        (already committed at payment_authorized time) — only
        payment_status moves. `data.refunded_amount` is the cumulative
        total refunded on the payment so far, so re-deriving REFUNDED vs.
        PARTIALLY_REFUNDED here is naturally idempotent: replaying the same
        cumulative amount always lands on the same status."""
        order = await self._locked(order_id)
        if order.payment_status not in {
            PaymentStatus.AUTHORIZED,
            PaymentStatus.CAPTURED,
            PaymentStatus.REFUNDED,
            PaymentStatus.PARTIALLY_REFUNDED,
        }:
            raise ServiceError(
                409, "invalid_order_state", "Order has no successful payment to refund"
            )
        if data.currency_code != order.currency_code:
            raise ServiceError(
                422, "payment_amount_mismatch", "Refund currency does not match order"
            )
        if data.refunded_amount > order.grand_total:
            raise ServiceError(
                422,
                "payment_amount_mismatch",
                "Refunded amount exceeds the order's grand total",
            )
        order.payment_status = (
            PaymentStatus.REFUNDED
            if data.refunded_amount == order.grand_total
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        order.version += 1
        self._event(order, "order.payment_refunded", request_id)
        self._audit(order, str(principal.subject), "order.payment_refunded", request_id)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def fulfillment(
        self,
        order_id: UUID,
        data: FulfillmentUpdate,
        principal: Principal,
        request_id: str | None,
    ) -> Order:
        order = await self._locked(order_id)
        allowed = {
            OrderStatus.CONFIRMED: OrderStatus.PROCESSING,
            OrderStatus.PROCESSING: OrderStatus.SHIPPED,
            OrderStatus.SHIPPED: OrderStatus.DELIVERED,
        }
        if allowed.get(order.status) != data.status:
            raise ServiceError(
                409, "invalid_order_transition", "Fulfillment status is out of sequence"
            )
        await self._transition(
            order,
            data.status,
            str(principal.subject),
            data.shipment_reference,
            request_id,
        )
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def _service_token(self, fallback: str) -> str:
        """Token used for internal calls order-service makes with its own
        authority rather than forwarding the caller's token: Inventory's
        commit/release endpoints (needs inventory:commit) and Cart's
        checked-out callback (needs cart:checkout). The caller's own
        bearer token (`fallback`) never carries either scope — forwarding
        it is only correct for calls the buyer is *directly* authorized to
        make (e.g. reserving/releasing their own cart's inventory during
        checkout itself). It's wrong for payment_authorized/payment_failed,
        called by Payment Service's orders:payment-scoped token, which
        grants nothing on Inventory. `auth_client` is optional so tests can
        keep constructing `OrderService` without it and passing whatever
        token they need forwarded.
        """
        if self.auth_client is None:
            return fallback
        return await self.auth_client.service_token()

    async def _locked(self, order_id: UUID) -> Order:
        order = await self.repo.get(order_id, lock=True)
        if not order:
            raise ServiceError(404, "order_not_found", "Order was not found")
        return order

    async def _transition(
        self,
        order: Order,
        new_status: OrderStatus,
        actor: str,
        reason: str | None,
        request_id: str | None,
    ) -> None:
        old = order.status
        order.status = new_status
        order.version += 1
        self.session.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status=old.value,
                to_status=new_status.value,
                actor_id=actor,
                reason=reason,
            )
        )
        self._event(order, f"order.{new_status.value}", request_id)
        self._audit(order, actor, f"order.{new_status.value}", request_id)

    def _event(self, order: Order, event_type: str, request_id: str | None) -> None:
        self.session.add(
            OutboxEvent(
                aggregate_id=order.id,
                event_type=event_type,
                correlation_id=request_id,
                payload={
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "customer_id": str(order.customer_id),
                    "status": order.status.value,
                    "total": str(order.grand_total),
                    "currency": order.currency_code,
                },
            )
        )

    def _audit(
        self, order: Order, actor: str, action: str, request_id: str | None
    ) -> None:
        self.session.add(
            AuditRecord(
                actor_id=actor,
                action=action,
                order_id=order.id,
                correlation_id=request_id,
                details={"status": order.status.value, "version": order.version},
            )
        )

    def _order_number(self, order_id: UUID) -> str:
        date = datetime.now(UTC).strftime("%Y%m%d")
        return f"{self.settings.order_number_prefix}-{date}-{order_id.hex[:10].upper()}"
