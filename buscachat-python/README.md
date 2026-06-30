# Buscachat Python

Servicio FastAPI + Postgres + pgvector para el chatbot de BuscaChat. Recibe
mensajes desde WhatsApp y desde el tester web, consulta la API de
Venezuela Te Busca para busquedas por nombre o cedula, y permite registrar o
comparar reportes por foto.

## Requisitos

- `uv`
- Docker o Docker Compose (imagen `pgvector/pgvector:pg18`)
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

Endpoints principales:

- `POST /whatsapp-meta-webhook`: webhook de WhatsApp Cloud API.
- `GET /web-chat`: tester web local.
- `POST /web-chat/webhook`: entrada del tester web.
- `GET /health` y `GET /health/db`: health checks de despliegue.

Documentacion interactiva:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Telemetria

La configuracion de OpenTelemetry/Honeycomb para produccion esta en
[`TELEMETRY.md`](TELEMETRY.md).

## Configuracion

```env
POSTGRES_HOST_PORT=15432
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:15432/buscachat_dev
VENEZUELA_TE_BUSCA_BASE_URL=https://venezuelatebusca.com
VENEZUELA_TE_BUSCA_TIMEOUT_SECONDS=20
BOT_SOURCE=whatsapp_bot
```

Si el host ya usa ese puerto, cambia `POSTGRES_HOST_PORT` y actualiza tambien el
puerto de `DATABASE_URL`.

### Reconocimiento facial

Por defecto `FACE_MATCHER=stub` (sin dependencias nativas) para que `pytest` y el
arranque sean ligeros. Para usar el motor real local instala el grupo opcional y
cambia la variable:

```bash
uv sync --group face
# .env
FACE_MATCHER=insightface
```

Los embeddings (512 dimensiones, modelo `buffalo_l` de InsightFace) se guardan
en `bot_reports.face_embedding` como columna `vector(512)` de **pgvector**. La
busqueda usa el operador `<=>` (distancia coseno) con un indice **HNSW**.

Variables relevantes:

```env
FACE_MATCHER=stub           # "stub" (defecto, sin deps nativas) | "insightface"
FACE_MATCH_THRESHOLD=0.35   # similitud coseno minima para considerar match
FACE_INSIGHTFACE_MODEL=buffalo_l
```

## Migraciones

Este proyecto usa Alembic. Las migraciones viven en `alembic/versions/*.py`.
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

## Pruebas

Pruebas rapidas:

```bash
uv run pytest
```

Pruebas e2e con Postgres real y efimero:

```bash
uv run pytest -m e2e
```

La prueba e2e del bot intake (`tests/test_bot_intake_e2e.py`) usa el contenedor
`pgvector/pgvector:pg18` para verificar el flujo completo: registrar persona con
embedding, busqueda sin match, busqueda con match y notificacion al reportante.

## Base de datos vectorial

La busqueda facial no usa un servicio dedicado. La extension **pgvector** corre
dentro del mismo Postgres:

- En desarrollo local: imagen `pgvector/pgvector:pg18` en `docker-compose.yml`.
- En produccion administrada (Supabase, Neon, RDS, etc.): ejecutar
  `CREATE EXTENSION IF NOT EXISTS vector` (la migracion `003` lo hace
  automaticamente).

La migracion `003_face_embedding_vector` convierte la columna JSONB heredada a
`vector(512)` y crea el indice HNSW con distancia coseno. Si la tabla tiene
datos previos con otra dimension, la migracion fallara; en ese caso usa
`DROP + ADD COLUMN` y re-genera los embeddings.
