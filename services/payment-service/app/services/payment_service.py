from __future__ import annotations

import hashlib
from uuid import UUID

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dependencies.auth import Principal
from app.exceptions import ServiceError
from app.models.payment import Payment, PaymentStatus, Refund, RefundStatus
from app.models.reliability import IdempotencyRecord, WebhookEvent
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import PaymentCreate, RefundCreate
from app.services.auth_client import AuthClient
from app.services.order_client import OrderClient
from app.services.stripe_client import StripeClient


class PaymentService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        stripe_client: StripeClient,
        order_client: OrderClient,
        auth_client: AuthClient,
    ) -> None:
        self.session = session
        self.settings = settings
        self.repo = PaymentRepository(session)
        self.stripe = stripe_client
        self.orders = order_client
        self.auth = auth_client

    # -- buyer-facing ------------------------------------------------

    async def create_payment(
        self,
        data: PaymentCreate,
        principal: Principal,
        buyer_token: str,
        idempotency_key: str | None,
        request_id: str | None,
    ) -> tuple[Payment, str | None]:
        request_hash = hashlib.sha256(
            data.model_dump_json().encode("utf-8")
        ).hexdigest()
        if idempotency_key:
            existing = await self.repo.get_idempotency_record(
                principal.subject, idempotency_key
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise ServiceError(
                        409,
                        "idempotency_conflict",
                        "Idempotency key was reused with another request",
                    )
                if existing.resource_id:
                    payment = await self.repo.get_payment(existing.resource_id)
                    if payment:
                        # client_secret is never persisted (see schema
                        # docstring); a replay can't re-serve it.
                        return payment, None

        if await self.repo.get_payment_by_order(data.order_id):
            raise ServiceError(
                409,
                "payment_already_exists",
                "A payment already exists for this order",
            )

        order = await self.orders.get_order(data.order_id, buyer_token, request_id)
        if order.status != "pending_payment":
            raise ServiceError(
                409, "order_not_payable", "Order is not awaiting payment"
            )

        intent = await self.stripe.create_payment_intent(
            order.grand_total,
            order.currency_code,
            metadata={
                "order_id": str(data.order_id),
                "customer_id": str(principal.subject),
            },
        )

        payment = Payment(
            order_id=data.order_id,
            customer_id=principal.subject,
            amount=order.grand_total,
            currency_code=order.currency_code,
            provider_payment_intent_id=intent.id,
            status=PaymentStatus.PENDING,
        )
        self.session.add(payment)
        await self.session.flush()

        if idempotency_key:
            self.session.add(
                IdempotencyRecord(
                    actor_id=principal.subject,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    resource_type="payment",
                    resource_id=payment.id,
                )
            )
        await self.session.commit()
        return payment, intent.client_secret

    async def get_payment(self, payment_id: UUID, principal: Principal) -> Payment:
        payment = await self.repo.get_payment(payment_id)
        if not payment:
            raise ServiceError(404, "payment_not_found", "Payment was not found")
        if payment.customer_id != principal.subject and not principal.has_role(
            "admin"
        ):
            raise ServiceError(404, "payment_not_found", "Payment was not found")
        return payment

    async def create_refund(
        self,
        payment_id: UUID,
        data: RefundCreate,
        principal: Principal,
        idempotency_key: str | None,
        request_id: str | None,
    ) -> Refund:
        request_hash = hashlib.sha256(
            f"{payment_id}:{data.model_dump_json()}".encode()
        ).hexdigest()
        if idempotency_key:
            existing = await self.repo.get_idempotency_record(
                principal.subject, idempotency_key
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise ServiceError(
                        409,
                        "idempotency_conflict",
                        "Idempotency key was reused with another request",
                    )
                if existing.resource_id:
                    refund = await self.repo.get_refund(existing.resource_id)
                    if refund:
                        return refund

        payment = await self.repo.get_payment(payment_id, for_update=True)
        if not payment:
            raise ServiceError(404, "payment_not_found", "Payment was not found")
        if payment.customer_id != principal.subject and not principal.has_role(
            "admin"
        ):
            raise ServiceError(404, "payment_not_found", "Payment was not found")
        if payment.status not in (
            PaymentStatus.SUCCEEDED,
            PaymentStatus.PARTIALLY_REFUNDED,
        ):
            raise ServiceError(
                409,
                "payment_not_refundable",
                "Only a succeeded payment can be refunded",
            )
        previously_refunded = payment.refunded_amount
        remaining = payment.amount - previously_refunded
        amount = data.amount if data.amount is not None else remaining
        if amount > remaining:
            raise ServiceError(
                422,
                "refund_exceeds_remaining",
                f"Only {remaining} remains available to refund",
            )

        provider_refund_id = await self.stripe.create_refund(
            payment.provider_payment_intent_id,
            data.amount,
            idempotency_key,
        )
        refund = Refund(
            payment_id=payment.id,
            provider_refund_id=provider_refund_id,
            amount=amount,
            reason=data.reason,
            status=RefundStatus.SUCCEEDED,
        )
        # Append to the relationship (not just session.add): payment.refunds
        # is already loaded (selectin) in this session's identity map, and a
        # bare session.add wouldn't update that in-memory collection — a
        # second refund on the same payment/session would then read a stale
        # (too-low) payment.refunded_amount on its next call.
        payment.refunds.append(refund)
        total_refunded = previously_refunded + amount
        payment.status = (
            PaymentStatus.REFUNDED
            if amount == remaining
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        payment.version += 1
        await self.session.flush()
        if idempotency_key:
            self.session.add(
                IdempotencyRecord(
                    actor_id=principal.subject,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    resource_type="refund",
                    resource_id=refund.id,
                )
            )
        # Commit before calling Order, unlike the webhook handlers below:
        # Stripe's refund API call above already moved real money, and this
        # buyer-facing endpoint has no Stripe-driven retrier behind it. If
        # we committed after a successful Order callback and that callback
        # failed, a buyer retry would call Stripe's refund API a second
        # time. Committing first means a failed callback only leaves
        # order.payment_status stale (recoverable) instead of risking a
        # duplicate refund (not recoverable).
        await self.session.commit()

        token = await self.auth.service_token()
        try:
            await self.orders.payment_refunded(
                payment.order_id,
                total_refunded,
                payment.currency_code,
                data.reason,
                token,
                request_id,
            )
        except ServiceError:
            # Refund already succeeded and is durably recorded above; the
            # order's payment_status will just lag until reconciled. Same
            # "best effort, don't fail the caller" shape as order-service's
            # own cart.mark_checked_out call in OrderService.create().
            pass
        return refund

    # -- webhook -------------------------------------------------------

    async def handle_webhook_event(
        self,
        event: stripe.Event,
        request_id: str | None,
    ) -> None:
        if await self.repo.get_webhook_event(event.id):
            return  # already processed; Stripe delivers at-least-once

        self.session.add(
            WebhookEvent(
                provider_event_id=event.id,
                event_type=event.type,
            )
        )

        if event.type == "payment_intent.succeeded":
            await self._on_payment_succeeded(event.data.object, request_id)
        elif event.type == "payment_intent.payment_failed":
            await self._on_payment_failed(event.data.object, request_id)
        else:
            await self.session.commit()
            return

    async def _on_payment_succeeded(self, intent, request_id: str | None) -> None:
        payment = await self.repo.get_payment_by_intent(intent.id, for_update=True)
        if not payment:
            await self.session.commit()
            return
        if payment.status == PaymentStatus.SUCCEEDED:
            await self.session.commit()
            return

        payment.status = PaymentStatus.SUCCEEDED
        payment.version += 1
        await self.session.flush()

        token = await self.auth.service_token()
        await self.orders.payment_authorized(
            payment.order_id,
            payment.provider_payment_intent_id,
            payment.amount,
            payment.currency_code,
            token,
            request_id,
        )
        await self.session.commit()

    async def _on_payment_failed(self, intent, request_id: str | None) -> None:
        payment = await self.repo.get_payment_by_intent(intent.id, for_update=True)
        if not payment:
            await self.session.commit()
            return
        if payment.status == PaymentStatus.FAILED:
            await self.session.commit()
            return

        reason = _decline_reason(intent)
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = reason
        payment.version += 1
        await self.session.flush()

        token = await self.auth.service_token()
        await self.orders.payment_failed(
            payment.order_id,
            payment.provider_payment_intent_id,
            reason,
            token,
            request_id,
        )
        await self.session.commit()


def _decline_reason(intent) -> str:
    last_error = getattr(intent, "last_payment_error", None)
    if last_error and getattr(last_error, "message", None):
        return str(last_error.message)
    return "payment_failed"
