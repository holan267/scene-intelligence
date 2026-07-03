#!/bin/sh
# Chạy migration (Postgres = SoT, AD-4) rồi khởi động API.
set -e
alembic upgrade head
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
