import pytest
from fastapi import HTTPException

from app.dependencies.headers import optional_idempotency_key, required_version


@pytest.mark.asyncio
async def test_if_match_parses_quoted_version() -> None:
    assert await required_version('"7"') == 7


@pytest.mark.asyncio
async def test_if_match_is_required() -> None:
    with pytest.raises(HTTPException) as exc:
        await required_version(None)
    assert exc.value.status_code == 428


@pytest.mark.asyncio
async def test_idempotency_key_length() -> None:
    with pytest.raises(HTTPException):
        await optional_idempotency_key("short")
    assert await optional_idempotency_key("product-create-001") == "product-create-001"

