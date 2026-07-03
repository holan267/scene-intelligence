FROM python:3.12-slim

WORKDIR /app

# uv để cài phụ thuộc nhanh, đóng băng theo pyproject
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Cài phụ thuộc TỪ pyproject (không hardcode -> không drift)
COPY pyproject.toml uv.lock* ./
RUN uv pip install --system .

COPY . .

EXPOSE 8000
CMD ["sh", "deploy/entrypoint.sh"]
