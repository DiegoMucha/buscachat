#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

# Safe defaults for a production-style local smoke run.
export FACE_MATCHER="${FACE_MATCHER:-stub}"
export NOTIFIER="${NOTIFIER:-null}"

uv sync --frozen --no-dev --group ocr
uv run alembic upgrade head

exec uv run python -m fastapi run main.py --host "$HOST" --port "$PORT"
