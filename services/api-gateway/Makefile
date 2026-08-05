.PHONY: install run test lint format check docker-up docker-down

install:
	uv sync

run:
	uv run uvicorn app.main:app --reload --port 9000

test:
	uv run pytest -q

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint test

docker-up:
	docker compose up --build

docker-down:
	docker compose down
