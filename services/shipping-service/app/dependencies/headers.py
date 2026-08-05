from typing import Annotated

from fastapi import Header, HTTPException, status


async def required_idempotency_key(
    idempotency_key: Annotated[str | None, Header()] = None,
) -> str:
    if idempotency_key is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )
    value = idempotency_key.strip()
    if not 8 <= len(value) <= 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must contain 8 to 100 characters",
        )
    return value
