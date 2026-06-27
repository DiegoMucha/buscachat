#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/buscachat-venezuela}"
SERVICE_NAME="${SERVICE_NAME:-buscachat-python}"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

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

UV_BIN="$(command -v uv || true)"
if [[ -z "$UV_BIN" ]]; then
  echo "uv was not found in PATH: $PATH" >&2
  exit 1
fi

cd "$APP_DIR/buscachat-python"
retry 5 5 "$UV_BIN" sync --frozen --no-dev
"$UV_BIN" run alembic upgrade head

sudo /usr/bin/systemctl restart "$SERVICE_NAME"
sudo /usr/bin/systemctl is-active --quiet "$SERVICE_NAME"
