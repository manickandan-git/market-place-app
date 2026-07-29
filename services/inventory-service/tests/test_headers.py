import pytest
from fastapi import HTTPException

from app.dependencies.headers import optional_idempotency_key, required_version


@pytest.mark.asyncio
async def test_if_match_accepts_quoted_version() -> None:
    assert await required_version('"v3"') == 3


@pytest.mark.asyncio
async def test_if_match_is_required() -> None:
    with pytest.raises(HTTPException) as error:
        await required_version(None)
    assert error.value.status_code == 428


@pytest.mark.asyncio
async def test_short_idempotency_key_is_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        await optional_idempotency_key("short")
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_valid_idempotency_key_is_trimmed() -> None:
    assert await optional_idempotency_key("  inventory-123  ") == "inventory-123"
