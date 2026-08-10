from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.dependencies.auth import Principal, bearer, require_roles
from app.dependencies.headers import optional_idempotency_key
from app.routes.dependencies import get_payment_service
from app.schemas.payment import (
    PaymentCreate,
    PaymentCreateResponse,
    PaymentResponse,
    RefundCreate,
    RefundResponse,
)
from app.services.payment_service import PaymentService

router = APIRouter()
Buyer = Annotated[Principal, Depends(require_roles("buyer", "admin"))]
Service = Annotated[PaymentService, Depends(get_payment_service)]
IdempotencyKey = Annotated[str | None, Depends(optional_idempotency_key)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Depends(bearer)
]


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _token(credentials: HTTPAuthorizationCredentials | None) -> str:
    return credentials.credentials if credentials else ""


@router.post(
    "/payments",
    response_model=PaymentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["payments"],
)
async def create_payment(
    data: PaymentCreate,
    request: Request,
    principal: Buyer,
    service: Service,
    credentials: BearerCredentials,
    idempotency_key: IdempotencyKey,
) -> PaymentCreateResponse:
    payment, client_secret = await service.create_payment(
        data,
        principal,
        _token(credentials),
        idempotency_key,
        _request_id(request),
    )
    return PaymentCreateResponse(
        payment=PaymentResponse.model_validate(payment),
        client_secret=client_secret,
    )


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
    tags=["payments"],
)
async def get_payment(
    payment_id: UUID,
    principal: Buyer,
    service: Service,
) -> PaymentResponse:
    payment = await service.get_payment(payment_id, principal)
    return PaymentResponse.model_validate(payment)


@router.post(
    "/payments/{payment_id}/refund",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["payments"],
)
async def create_refund(
    payment_id: UUID,
    data: RefundCreate,
    request: Request,
    principal: Buyer,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> RefundResponse:
    refund = await service.create_refund(
        payment_id, data, principal, idempotency_key, _request_id(request)
    )
    return RefundResponse.model_validate(refund)
