#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/buscachat-venezuela}"
SERVICE_NAME="${SERVICE_NAME:-buscachat-python}"
ENV_FILE="${ENV_FILE:-$APP_DIR/buscachat-python/.env.production}"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

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
retry 5 5 "$UV_BIN" sync --frozen --no-dev --group ocr
"$UV_BIN" run alembic upgrade head

sudo /usr/bin/systemctl daemon-reload
sudo /usr/bin/systemctl restart "$SERVICE_NAME"
sudo /usr/bin/systemctl is-active --quiet "$SERVICE_NAME" || exit 1

echo "Waiting for service to be ready..."
sleep 3
for i in $(seq 1 10); do
  if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "Health check passed"
    exit 0
  fi
  if [ "$i" -eq 10 ]; then
    echo "Health check failed after 10 attempts"
    exit 1
  fi
  echo "Attempt $i failed, retrying in 3s..."
  sleep 3
done
