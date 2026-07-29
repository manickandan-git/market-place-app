.PHONY: install lint test run migrate docker-up docker-down

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

docker-up:
	docker compose up --build

docker-down:
	docker compose down
