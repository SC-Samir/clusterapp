#!/usr/bin/env bash
set -euo pipefail

echo "[1/5] Start Postgres + pgvector"
docker compose up -d db

echo "[2/5] Wait for DB health"
until [ "$(docker inspect -f '{{.State.Health.Status}}' lecpac_pgvector 2>/dev/null || true)" = "healthy" ]; do
  sleep 1
done

echo "[3/5] Setup Python env"
uv sync

echo "[4/5] Run migrations"
cp .env.docker .env
uv run alembic upgrade head

echo "[5/5] Start API"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
