.PHONY: install run test lint format migrate docker-up docker-down

install:
	uv sync
run:
	uv run uvicorn app.main:app --reload --port 8003
test:
	uv run pytest
lint:
	uv run ruff check .
format:
	uv run ruff format .
migrate:
	uv run alembic upgrade head
docker-up:
	docker compose up --build
docker-down:
	docker compose down
