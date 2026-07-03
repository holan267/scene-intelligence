FROM python:3.12-slim

WORKDIR /app

# uv để cài phụ thuộc nhanh, đóng băng theo pyproject
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml ./
RUN uv pip install --system fastapi "uvicorn[standard]" pydantic-settings \
    "sqlalchemy[asyncio]" "psycopg[binary]" alembic

COPY . .

EXPOSE 8000
CMD ["sh", "deploy/entrypoint.sh"]
