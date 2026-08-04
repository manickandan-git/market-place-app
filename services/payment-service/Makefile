.PHONY: install run test lint format migrate check docker-up docker-down

install:
	uv sync

run:
	uv run uvicorn app.main:app --reload --port 8008

test:
	uv run pytest -q

lint:
	uv run ruff check .

format:
	uv run ruff format .

migrate:
	uv run alembic upgrade head

check: lint test

docker-up:
	docker compose up --build

docker-down:
	docker compose down
