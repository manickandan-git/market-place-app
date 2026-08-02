from typing import Annotated

from fastapi import Header

from app.exceptions import ServiceError


async def optional_guest_token(
    value: Annotated[str | None, Header(alias="X-Cart-Token")] = None,
) -> str | None:
    if value is not None and not 32 <= len(value) <= 200:
        raise ServiceError(400, "invalid_cart_token", "X-Cart-Token is invalid")
    return value


async def optional_idempotency_key(
    value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    if value is not None and not 8 <= len(value) <= 100:
        raise ServiceError(
            400,
            "invalid_idempotency_key",
            "Idempotency-Key must contain 8 to 100 characters",
        )
    return value


async def required_version(
    value: Annotated[int | None, Header(alias="If-Match-Version")] = None,
) -> int:
    if value is None or value < 1:
        raise ServiceError(
            428,
            "version_required",
            "If-Match-Version header is required and must be positive",
        )
    return value
