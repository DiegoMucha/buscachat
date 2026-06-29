# Buscachat Python

Servicio FastAPI + Postgres + pgvector para sincronizar reportes de personas
desde fuentes externas, recibir reportes por bot (WhatsApp/Telegram) y
emparejar rostros entre personas desaparecidas y halladas.

La primera fuente implementada es:

```text
https://sosvenezuela2026.com/api/persons/list
```

La sincronizacion es interna. FastAPI inicia APScheduler desde el `lifespan` de
la app y ejecuta el job cada 2 horas.

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

Los embeddings (512 dimensiones, modelo `buffalo_l` de InsightFace) se guardan
en `bot_reports.face_embedding` como columna `vector(512)` de **pgvector**. La
busqueda usa el operador `<=>` (distancia coseno) con un indice **HNSW**, lo
que evita recorrer toda la tabla y escala a miles de registros sin re-arquitectura.

Variables relevantes:

```env
FACE_MATCHER=stub           # "stub" (defecto, sin deps nativas) | "insightface"
FACE_MATCH_THRESHOLD=0.35   # similitud coseno minima para considerar match
FACE_INSIGHTFACE_MODEL=buffalo_l
```

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

La prueba e2e de sync inicia un contenedor Postgres con testcontainers, ejecuta
todas las migraciones, corre el sync a traves de la capa adapter/service y
verifica upserts en `missing_people`, `source_records` y `sync_state`.

La prueba e2e del bot intake (`tests/test_bot_intake_e2e.py`) usa el contenedor
`pgvector/pgvector:pg18` para verificar el flujo completo: registrar persona con
embedding → busqueda sin match → busqueda con match → notificacion al reportante.

## Base de datos vectorial

La busqueda facial no usa un servicio dedicado. La extension **pgvector** corre
dentro del mismo Postgres:

- En desarrollo local: imagen `pgvector/pgvector:pg18` en `docker-compose.yml`.
- En produccion administrada (Supabase, Neon, RDS, etc.): ejecutar
  `CREATE EXTENSION IF NOT EXISTS vector` (la migra-cion `003` lo hace
  automaticamente).

La migracion `003_face_embedding_vector` convierte la columna JSONB heredada a
`vector(512)` y crea el indice HNSW con distancia coseno. Si la tabla tiene
datos previos con otra dimension, la migracion fallara; en ese caso usa
`DROP + ADD COLUMN` y re-genera los embeddings.

## Generar embeddings para registros sincronizados

Los registros que vienen del sync de SOS Venezuela (`sosvenezuela2026.com`)
tienen `photo_url` pero **no** un embedding facial. Sin embedding no pueden
encontrarse por reconocimiento facial.

El script `scripts/generate_embeddings.py` descarga las fotos pendientes,
genera el embedding con InsightFace y crea un `BotReport` vinculado al
`MissingPerson`. **Debe ejecutarse desde la carpeta `buscachat-python`:**

```bash
cd buscachat-python

# Procesar los primeros 10 registros (prueba)
uv run python scripts/generate_embeddings.py --max 10

# Procesar todos los pendientes
uv run python scripts/generate_embeddings.py --max 0
```

**Requisitos:**
- `FACE_MATCHER=insightface` en `.env` (el stub no reconoce rostros reales)
- Dependencias instaladas: `uv sync --group face`
- Postgres con extension `vector` (la migracion 003 la crea)

**Que hace el script:**
1. Busca `missing_people` con `photo_url` que **no** tengan un `bot_reports`
   con `face_embedding`.
2. Descarga cada foto (timeout 30s, con reintentos via httpx).
3. Genera el vector facial de 512 dimensiones con InsightFace.
4. Crea un `BotReport` con `channel=sosvenezuela2026`, `face_embedding`
   y `status` igual al del `MissingPerson`.
5. Si la foto no tiene una cara detectable, la saltea.
6. Si la URL esta rota o el servidor no responde, registra el error y
   sigue con la siguiente.

Al final imprime: `Exitosos`, `Fallidos`, `Saltados`.

**Ejecutar despues de cada sync** para mantener los embeddings al dia:

```bash
cd buscachat-python
uv run python scripts/generate_embeddings.py --max 100
```
