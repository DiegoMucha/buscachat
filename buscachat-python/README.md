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
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/buscachat_dev
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
las migraciones SQL, corre el sync a traves de la capa adapter/service, y
verifica upserts en `missing_people`, `source_records` y `sync_state`.
