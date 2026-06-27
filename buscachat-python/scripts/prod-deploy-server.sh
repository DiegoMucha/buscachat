#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/buscachat-venezuela}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-buscachat-python}"

retry() {
  local attempts="$1"
  local delay="$2"
  shift 2

  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi

    if (( attempt >= attempts )); then
      echo "Command failed after $attempt attempts: $*" >&2
      return 1
    fi

    echo "Command failed, retrying in ${delay}s ($attempt/$attempts): $*" >&2
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
  done
}

cd "$APP_DIR"
retry 5 5 git fetch origin "$BRANCH"
git checkout "$BRANCH"
git merge --ff-only FETCH_HEAD

cd "$APP_DIR/buscachat-python"
retry 5 5 uv sync --frozen --no-dev
uv run alembic upgrade head

sudo /usr/bin/systemctl restart "$SERVICE_NAME"
sudo /usr/bin/systemctl is-active --quiet "$SERVICE_NAME"
