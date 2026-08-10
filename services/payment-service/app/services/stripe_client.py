from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import stripe

from app.config import Settings
from app.exceptions import ServiceError


@dataclass(frozen=True)
class StripePaymentIntent:
    id: str
    client_secret: str | None
    status: str


def to_minor_units(amount: Decimal) -> int:
    """Stripe amounts are integers in the currency's smallest unit (cents
    for USD). Assumes 2-decimal currencies only — zero-decimal currencies
    (e.g. JPY) are out of scope for now."""
    return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_minor_units(amount: int) -> Decimal:
    return (Decimal(amount) / 100).quantize(Decimal("0.01"))


class StripeClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        stripe.api_key = settings.stripe_secret_key

    async def create_payment_intent(
        self,
        amount: Decimal,
        currency_code: str,
        metadata: dict[str, str],
    ) -> StripePaymentIntent:
        try:
            intent = await stripe.PaymentIntent.create_async(
                amount=to_minor_units(amount),
                currency=currency_code.lower(),
                metadata=metadata,
                automatic_payment_methods={"enabled": True},
            )
        except stripe.StripeError as exc:
            raise ServiceError(502, "stripe_error", str(exc)) from exc
        return StripePaymentIntent(
            id=intent.id, client_secret=intent.client_secret, status=intent.status
        )

    async def create_refund(
        self,
        payment_intent_id: str,
        amount: Decimal | None,
        idempotency_key: str | None = None,
    ) -> str:
        try:
            kwargs: dict = {"payment_intent": payment_intent_id}
            if amount is not None:
                kwargs["amount"] = to_minor_units(amount)
            if idempotency_key:
                kwargs["idempotency_key"] = f"refund:{idempotency_key}"
            refund = await stripe.Refund.create_async(**kwargs)
        except stripe.StripeError as exc:
            raise ServiceError(502, "stripe_error", str(exc)) from exc
        return refund.id

    def construct_webhook_event(self, payload: bytes, signature: str) -> stripe.Event:
        try:
            return stripe.Webhook.construct_event(
                payload, signature, self.settings.stripe_webhook_secret
            )
        except ValueError as exc:
            raise ServiceError(
                400, "invalid_webhook_payload", "Malformed webhook payload"
            ) from exc
        except stripe.SignatureVerificationError as exc:
            raise ServiceError(
                400, "invalid_webhook_signature", "Invalid webhook signature"
            ) from exc
