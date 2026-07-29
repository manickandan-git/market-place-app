import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://inventory:inventory@localhost:5435/inventory_service",
)
