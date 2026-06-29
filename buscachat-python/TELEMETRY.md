# Telemetry

This service uses OpenTelemetry auto-instrumentation and exports traces to
Honeycomb over OTLP HTTP/protobuf.

## Local setup

Install the project dependencies:

```bash
uv sync
```

## Required production environment

Edit the production env file on the server:

```bash
sudo -u lozabot nano /home/lozabot/buscachat-venezuela/buscachat-python/.env.production
```

Set these variables:

```env
OTEL_SERVICE_NAME=buscachat-python
OTEL_TRACES_EXPORTER=otlp
OTEL_METRICS_EXPORTER=none
OTEL_LOGS_EXPORTER=none
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=<honeycomb-api-key>
```

`OTEL_SERVICE_NAME` is used by Honeycomb as the Service Dataset name. Use the
Honeycomb ingest key as `<honeycomb-api-key>`. Do not commit the real key.

## Production deploy and restart

From the server, deploy the latest code and restart the service:

```bash
cd /home/lozabot/buscachat-venezuela
git pull
cd buscachat-python
uv sync --frozen --no-dev
uv run alembic upgrade head
sudo systemctl daemon-reload
sudo systemctl restart buscachat-python
sudo systemctl status buscachat-python --no-pager
```

For non-interactive deploys, the deploy user needs passwordless sudo for the
systemctl commands used by `scripts/prod-deploy-server.sh`. Add or update a
sudoers drop-in on the production server:

```bash
sudo visudo -f /etc/sudoers.d/buscachat-python
```

Use the user that runs the deploy. For the default `lozabot` user:

```sudoers
lozabot ALL=(root) NOPASSWD: /usr/bin/systemctl daemon-reload, /usr/bin/systemctl restart buscachat-python, /usr/bin/systemctl is-active --quiet buscachat-python
```

The systemd unit starts the app through OpenTelemetry:

```bash
/home/lozabot/.local/bin/uv run opentelemetry-instrument python -m fastapi run main.py --host 127.0.0.1 --port 8000
```

Check logs after restart:

```bash
sudo journalctl -u buscachat-python -n 100 --no-pager
```

Generate a request so a trace is emitted:

```bash
curl -sf http://127.0.0.1:8000/health
```

Then check Honeycomb for the `buscachat-python` service dataset.
