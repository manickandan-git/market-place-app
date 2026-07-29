"""Guard against the "model defines a table the migration never creates" gap
found in user-service this session (OutboxEvent/IdempotencyRecord were
modeled but absent from the initial migration, only discovered via live
testing). Every table SQLAlchemy knows about must have a matching
op.create_table(...) call in the single migration.
"""

import re
from pathlib import Path

import app.models  # noqa: F401  ensures every model module is imported/registered
from app.models.base import Base

MIGRATION_PATH = (
    Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "001_create_product_catalog.py"
)

CREATE_TABLE_PATTERN = re.compile(r'op\.create_table\(\s*\n?\s*"(\w+)"')


def test_every_model_table_is_created_by_the_migration() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    created_tables = set(CREATE_TABLE_PATTERN.findall(source))
    model_tables = set(Base.metadata.tables.keys())
    missing = model_tables - created_tables
    assert not missing, (
        f"Migration 001 never creates table(s): {sorted(missing)} — "
        "every SQLAlchemy model needs a matching op.create_table() call"
    )


def test_migration_creates_no_unknown_tables() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    created_tables = set(CREATE_TABLE_PATTERN.findall(source))
    model_tables = set(Base.metadata.tables.keys())
    extra = created_tables - model_tables
    assert not extra, (
        f"Migration 001 creates table(s) with no matching model: {sorted(extra)}"
    )
