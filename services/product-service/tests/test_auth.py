from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.dependencies.auth import Principal, _as_set, require_roles


def test_claim_collection_supports_space_delimited_value() -> None:
    assert _as_set("seller catalog:write") == {"seller", "catalog:write"}


def test_principal_role_check() -> None:
    principal = Principal(
        subject=uuid4(),
        roles=frozenset({"seller"}),
        scopes=frozenset(),
        claims={},
    )
    assert principal.has_role("seller", "admin")
    assert not principal.has_role("buyer")


@pytest.mark.asyncio
async def test_required_role_rejects_buyer() -> None:
    principal = Principal(
        subject=uuid4(),
        roles=frozenset({"buyer"}),
        scopes=frozenset(),
        claims={},
    )
    dependency = require_roles("seller", "admin")
    with pytest.raises(HTTPException) as exc:
        await dependency(principal)
    assert exc.value.status_code == 403

