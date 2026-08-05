from __future__ import annotations

import hashlib
import hmac
import json
import time
from uuid import uuid4


def sign_stripe_payload(secret: str, payload: bytes) -> str:
    """Builds a `Stripe-Signature` header the real `stripe` SDK's
    `Webhook.construct_event` will accept: `t=<unix_ts>,v1=<hex hmac-sha256
    of "<ts>.<raw_body>">`. This is what lets payment-service's webhook
    route be tested without `stripe listen` running — see
    docker-compose.yml's STRIPE_WEBHOOK_SECRET comment."""
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode()
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def build_payment_intent_event(
    event_type: str,
    payment_intent_id: str,
    *,
    decline_message: str | None = None,
) -> bytes:
    """Minimal Stripe Event envelope for payment_intent.succeeded /
    payment_intent.payment_failed. `stripe.Webhook.construct_event` only
    verifies the signature and JSON-decodes the body into a generic
    StripeObject — it doesn't require the full real API schema, just the
    fields payment-service's webhook handler actually reads (event.type,
    event.data.object.id, and last_payment_error.message on failure)."""
    intent: dict = {
        "id": payment_intent_id,
        "object": "payment_intent",
        "status": (
            "succeeded"
            if event_type == "payment_intent.succeeded"
            else "requires_payment_method"
        ),
    }
    if decline_message:
        intent["last_payment_error"] = {"message": decline_message}
    event = {
        "id": f"evt_{uuid4().hex[:24]}",
        "object": "event",
        "type": event_type,
        "created": int(time.time()),
        "livemode": False,
        "data": {"object": intent},
    }
    return json.dumps(event).encode("utf-8")
