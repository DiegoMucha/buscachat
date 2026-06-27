# Buscachat Python

Servicio FastAPI + Postgres para sincronizar reportes de personas desde fuentes
externas y guardarlos en nuestra propia base de datos.

La primera fuente implementada es:

```text
https://sosvenezuela2026.com/api/persons/list
```

La sincronizacion es interna. FastAPI inicia APScheduler desde el `lifespan` de
la app y ejecuta el job cada 2 horas.

## Requisitos

- `uv`
- Docker o Docker Compose
- Docker local para correr pruebas e2e con testcontainers

## Setup

```bash
cp .env.sample .env
uv sync --dev
docker compose up -d
```

## Ejecutar la API

```bash
uv run python -m fastapi dev main.py
```

`uv run fastapi dev app/main.py` tambien funciona despues de `uv sync --dev`,
pero `python -m fastapi` evita problemas si un entorno virtual viejo quedo con
entrypoints apuntando a otra carpeta.

Documentacion interactiva:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Configuracion

```env
POSTGRES_HOST_PORT=15432
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:15432/buscachat_dev
PRIVATE_API_TOKEN=dev-hackathon-token
SOS_VENEZUELA_PERSONS_URL=https://sosvenezuela2026.com/api/persons/list
MISSING_PEOPLE_SYNC_ENABLED=true
MISSING_PEOPLE_SYNC_RUN_ON_STARTUP=true
MISSING_PEOPLE_SYNC_INTERVAL_HOURS=2
MISSING_PEOPLE_SYNC_PAGE_LIMIT=100
# MISSING_PEOPLE_SYNC_MAX_PAGES=10
MISSING_PEOPLE_SYNC_RETRY_ATTEMPTS=3
MISSING_PEOPLE_SYNC_RETRY_BACKOFF_SECONDS=1
```

Para desarrollo local, usa `MISSING_PEOPLE_SYNC_MAX_PAGES=1` si quieres que el
sync inicial descargue solo una pagina.

Si el host ya usa ese puerto, cambia `POSTGRES_HOST_PORT` y actualiza tambien el
puerto de `DATABASE_URL`.

## Bot intake (WhatsApp / Telegram)

El endpoint `POST /bot/chat` recibe la salida del nodo **Motor Conversacional**
del bot (n8n) y la ejecuta de verdad contra la base de datos. Despacha por el
campo `accion`:

- `registrar_persona`: descarga la foto (`imagen_ref`), calcula su embedding
  facial, crea una fila en `missing_people` y un `bot_reports` enlazado con los
  datos del bot, el contacto y el historial de conversacion.
- `buscar_por_foto`: compara la foto contra los registros del bot. Si hay match
  por encima de `FACE_MATCH_THRESHOLD`, marca a la persona como `found` y
  notifica al reportante original por WhatsApp (Green API). Si no hay match, no
  retorna datos de ninguna persona.
- `buscar_por_nombre`: reutiliza la busqueda por nombre existente.

En n8n: tras **Motor Conversacional**, agrega un **Switch** sobre
`{{ $json.accion }}` y enchufa un HTTP Request `POST /bot/chat` enviando el item
completo.

### Reconocimiento facial

Por defecto `FACE_MATCHER=stub` (sin dependencias nativas) para que `pytest` y el
arranque sean ligeros. Para usar el motor real local instala el grupo opcional y
cambia la variable:

```bash
uv sync --group face
# .env
FACE_MATCHER=insightface
```

Los embeddings se guardan en `bot_reports.face_embedding` (JSONB) y la
comparacion se hace por similitud coseno en Python.

## Migraciones

Este proyecto usa Alembic. Las migraciones viven en `alembic/versions/*.py`.
Alembic puede crear migraciones candidatas automaticamente comparando la base
de datos actual con los modelos SQLModel en `app/models.py`.

Importante: `--autogenerate` no reemplaza la revision humana. Funciona bien
para cambios obvios como tablas, columnas, indices y constraints con nombre,
pero renombres y cambios de datos se deben ajustar a mano en la revision.

Las migraciones corren automaticamente al iniciar FastAPI:

```bash
uv run python -m fastapi dev main.py
```

Tambien puedes aplicarlas manualmente:

```bash
uv run alembic upgrade head
```

Para crear una migracion nueva durante desarrollo:

1. Actualiza los modelos en `app/models.py`.
2. Genera la revision candidata:

```bash
uv run alembic revision --autogenerate -m "descripcion_del_cambio"
```

3. Revisa y corrige el archivo generado en `alembic/versions/`.
4. Aplica la migracion localmente:

```bash
uv run alembic upgrade head
```

5. Verifica que no quede drift entre modelos y DB:

```bash
uv run alembic check
```

6. Corre las pruebas rapidas y e2e:

```bash
uv run pytest
uv run pytest -m e2e
```

Cada revision se aplica una sola vez y queda registrada por Alembic en
`alembic_version`.

Para repetir la primera migracion en una DB local sin datos importantes:

```bash
uv run alembic downgrade base
uv run alembic upgrade head
```

Si tu DB local venia del runner SQL anterior, resetea el volumen y aplica
Alembic desde cero:

```bash
docker compose down -v
docker compose up -d
uv run alembic upgrade head
```

## Pruebas

Pruebas rapidas:

```bash
uv run pytest
```

Pruebas e2e con Postgres real y efimero:

```bash
uv run pytest -m e2e
```

La prueba e2e inicia un contenedor Postgres con testcontainers, ejecuta todas
las migraciones Alembic, corre el sync a traves de la capa adapter/service, y
verifica upserts en `missing_people`, `source_records` y `sync_state`.

## Produccion local

El smoke de produccion usa dependencias sin dev, aplica migraciones y arranca
FastAPI sin reload:

```bash
HOST=127.0.0.1 PORT=8000 ./scripts/prod-smoke.sh
```

## Ejecutar en produccion

Preparar el directorio de la app:

```bash
export APP_DIR=/home/lozabot/buscachat-venezuela
git clone git@github.com:DiegoMucha/buscachat.git "$APP_DIR"
cd "$APP_DIR/buscachat-python"
uv sync --frozen --no-dev
```

Crear el archivo de entorno:

```bash
cp deploy/production.env.sample .env.production
nano .env.production
```

Valores minimos a revisar en `.env.production`:

```env
DATABASE_URL=postgresql+psycopg://...
PRIVATE_API_TOKEN=...
FACE_MATCHER=stub
NOTIFIER=null
```

Instalar y arrancar systemd:

```bash
sudo cp deploy/buscachat-python.service /etc/systemd/system/buscachat-python.service
sudo systemctl daemon-reload
uv run alembic upgrade head
sudo systemctl enable --now buscachat-python
sudo systemctl status buscachat-python
```

Permitir que GitHub Actions reinicie solo este servicio:

```bash
sudo tee /etc/sudoers.d/buscachat-python >/dev/null <<'EOF'
lozabot ALL=(root) NOPASSWD: /usr/bin/systemctl restart buscachat-python, /usr/bin/systemctl is-active buscachat-python
EOF
sudo chmod 0440 /etc/sudoers.d/buscachat-python
sudo visudo -cf /etc/sudoers.d/buscachat-python
```

Probar el deploy manual en el servidor:

```bash
APP_DIR=/home/lozabot/buscachat-venezuela \
BRANCH=main \
SERVICE_NAME=buscachat-python \
./scripts/prod-deploy-server.sh
```

GitHub Actions despliega en cada push a `main` que toque `buscachat-python/**`.
El secret requerido es `SERVER_SSH_DEPLOY_KEY`, con la llave privada que conecta
como `lozabot@ssh.sumak.space`. El clone del servidor debe poder hacer
`git pull --ff-only origin main`.
