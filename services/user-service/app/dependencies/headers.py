from fastapi import Header, HTTPException, status


def parse_if_match(if_match: str | None = Header(default=None, alias="If-Match")) -> int:
    if if_match is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match header required"
        )
    value = if_match.strip().strip('"')
    if not value.isdigit() or int(value) < 1:
        raise HTTPException(status_code=400, detail='If-Match must contain a version, e.g. "1"')
    return int(value)


def require_idempotency_key(
    key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str:
    if not key or len(key) > 200:
        raise HTTPException(status_code=400, detail="Valid Idempotency-Key header required")
    return key
