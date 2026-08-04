from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.routes.dependencies import get_payment_service
from app.services.payment_service import PaymentService

router = APIRouter()
Service = Annotated[PaymentService, Depends(get_payment_service)]


@router.post("/webhooks/stripe", tags=["webhooks"])
async def stripe_webhook(
    request: Request,
    service: Service,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> dict[str, bool]:
    # Not JWT-authenticated: Stripe can't hold a marketplace-issued token.
    # Authenticity comes entirely from the signature below, verified
    # against STRIPE_WEBHOOK_SECRET.
    payload = await request.body()
    event = service.stripe.construct_webhook_event(payload, stripe_signature or "")
    await service.handle_webhook_event(
        event, getattr(request.state, "request_id", None)
    )
    return {"received": True}
