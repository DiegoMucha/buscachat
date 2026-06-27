#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/buscachat-venezuela}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-buscachat-python}"

cd "$APP_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

cd "$APP_DIR/buscachat-python"
uv sync --frozen --no-dev
uv run alembic upgrade head

sudo /usr/bin/systemctl restart "$SERVICE_NAME"
sudo /usr/bin/systemctl is-active --quiet "$SERVICE_NAME"
