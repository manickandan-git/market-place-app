from typing import Annotated

from fastapi import Header, HTTPException, status


async def required_version(
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> int:
    if if_match is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="If-Match header is required",
        )
    normalized = if_match.strip().strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="If-Match must contain a positive integer version",
        )
    return int(normalized)


async def optional_idempotency_key(
    value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    if value is not None and not 8 <= len(value.strip()) <= 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must be between 8 and 100 characters",
        )
    return value.strip() if value else None

