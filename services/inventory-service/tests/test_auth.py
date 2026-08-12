from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.dependencies.auth import Principal, _as_set, require_roles, require_scope


def test_claim_sets_support_space_delimited_values() -> None:
    assert _as_set("inventory:sync inventory:expire") == {
        "inventory:sync",
        "inventory:expire",
    }


def test_principal_role_check() -> None:
    principal = Principal(
        subject=uuid4(),
        roles=frozenset({"seller"}),
        scopes=frozenset(),
        claims={},
    )
    assert principal.has_role("seller", "admin")
    assert not principal.has_role("admin")


@pytest.mark.asyncio
async def test_role_dependency_rejects_buyer() -> None:
    principal = Principal(
        subject=uuid4(),
        roles=frozenset({"buyer"}),
        scopes=frozenset(),
        claims={},
    )
    dependency = require_roles("seller", "admin")
    with pytest.raises(HTTPException) as error:
        await dependency(principal)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_scope_dependency_accepts_service_scope() -> None:
    principal = Principal(
        subject=uuid4(),
        roles=frozenset({"service"}),
        scopes=frozenset({"inventory:sync"}),
        claims={},
    )
    dependency = require_scope("inventory:sync")
    assert await dependency(principal) == principal


@pytest.mark.asyncio
async def test_admin_satisfies_service_scope() -> None:
    principal = Principal(
        subject=uuid4(),
        roles=frozenset({"admin"}),
        scopes=frozenset(),
        claims={},
    )
    dependency = require_scope("inventory:expire")
    assert await dependency(principal) == principal


@pytest.mark.asyncio
async def test_scope_dependency_rejects_buyer_without_scope() -> None:
    principal = Principal(
        subject=uuid4(),
        roles=frozenset({"buyer"}),
        scopes=frozenset(),
        claims={},
    )
    dependency = require_scope("inventory:checkout")
    with pytest.raises(HTTPException) as error:
        await dependency(principal)
    assert error.value.status_code == 403
