from typing import Annotated

from fastapi import Header, HTTPException, status


async def required_version(
    if_match: Annotated[str | None, Header()] = None,
) -> int:
    if not if_match:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="If-Match header is required",
        )
    value = if_match.strip().strip('"')
    if value.startswith("v"):
        value = value[1:]
    try:
        version = int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="If-Match must be an integer version",
        ) from exc
    if version < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="If-Match version must be positive",
        )
    return version


async def optional_idempotency_key(
    idempotency_key: Annotated[str | None, Header()] = None,
) -> str | None:
    if idempotency_key is None:
        return None
    value = idempotency_key.strip()
    if not 8 <= len(value) <= 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must contain 8 to 100 characters",
        )
    return value
