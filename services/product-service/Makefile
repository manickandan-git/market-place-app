.PHONY: install lint test run migrate check

install:
	uv sync

lint:
	uv run ruff check .

test:
	uv run pytest -q

run:
	uv run uvicorn app.main:app --reload --port 8004

migrate:
	uv run alembic upgrade head

check: lint test

