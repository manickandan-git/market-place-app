FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN uv sync --no-dev
EXPOSE 8012
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8012"]
