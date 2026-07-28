import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://product:product@localhost:5434/product_service",
)

