"""Guard against the model/migration enum drift found in user-service this
session: a SQLAlchemy model enum and the Alembic migration's CHECK-constraint
enum must list the exact same values, or writes succeed in the ORM's own
round-trip but fail against a real (or differently-seeded) database.

This service's enums are stored by member *name* (e.g. "DRAFT"), not by
`.value` ("draft") — no `values_callable` is passed to `sa.Enum(...)` in
either the model or the migration, so SQLAlchemy's default name-based
enum binding applies on both sides consistently. The comparison here is
therefore against `[member.name for member in EnumClass]`, not `.value`.
"""

import re
from pathlib import Path

from app.models.catalog import ProductStatus

MIGRATION_PATH = (
    Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "001_create_product_catalog.py"
)

ENUM_CALL_PATTERN = re.compile(
    r'sa\.Enum\(\s*((?:"[^"]+",?\s*)+)name="(\w+)"', re.MULTILINE
)


def _migration_enum_values() -> dict[str, list[str]]:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    values_by_name: dict[str, list[str]] = {}
    for match in ENUM_CALL_PATTERN.finditer(source):
        literal_block, enum_name = match.groups()
        values_by_name[enum_name] = re.findall(r'"([^"]+)"', literal_block)
    return values_by_name


def test_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file(), f"Expected migration at {MIGRATION_PATH}"


def test_product_status_matches_migration() -> None:
    migration_values = _migration_enum_values()
    assert "product_status" in migration_values, (
        "Migration no longer defines a product_status enum — "
        "update this test if the enum was renamed or removed"
    )
    expected = [member.name for member in ProductStatus]
    assert migration_values["product_status"] == expected
