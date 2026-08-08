.PHONY: install run test lint format migrate seed check docker-up docker-down

install:
	uv sync

run:
	uv run uvicorn app.main:app --reload --port 8012

test:
	uv run pytest -q

lint:
	uv run ruff check .

format:
	uv run ruff format .

migrate:
	uv run alembic upgrade head

seed:
	uv run python -m app.rag.seed

check: lint test

docker-up:
	docker compose up --build

docker-down:
	docker compose down
