from contextlib import asynccontextmanager
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.database import get_session, run_migrations
from app.models import MissingPerson, SyncState, utc_now
from app.routers import bot as bot_router
from app.routers import web_chat as web_chat_router
from app.routers import whatsapp_evolution_api_webhook as evolution_api_webhook_router
from app.routers import whatsapp_green_api_webhook as green_api_webhook_router
from app.routers import whatsapp_meta_webhook as meta_webhook_router
from app.scheduler import start_scheduler
from app.security import require_private_token
from app.services.search import find_missing_person_by_name


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # run_migrations()
    # scheduler = start_scheduler(settings)
    # app.state.scheduler = scheduler
    try:
        yield
    finally:
        if isinstance(scheduler, BackgroundScheduler):
            scheduler.shutdown(wait=False)


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.include_router(bot_router.router)
app.include_router(web_chat_router.router)
app.include_router(evolution_api_webhook_router.router)
app.include_router(green_api_webhook_router.router)
app.include_router(meta_webhook_router.router)


@app.get("/health")
def health_check(session: Annotated[Session, Depends(get_session)]) -> dict:
    db_ok = False
    try:
        session.exec(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "timestamp": utc_now().isoformat(),
    }


@app.get("/health/db")
def database_health(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    session.exec(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/missing_people", response_model=list[MissingPerson])
def list_missing_people(
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=50)] = None,
    source: Annotated[str | None, Query(max_length=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[MissingPerson]:
    statement = select(MissingPerson)

    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            MissingPerson.full_name.ilike(pattern)
            | MissingPerson.last_known_location.ilike(pattern)
        )
    if status_filter:
        statement = statement.where(MissingPerson.status == status_filter)
    if source:
        statement = statement.where(MissingPerson.source == source)

    statement = (
        statement.order_by(
            MissingPerson.source_date.desc().nullslast(), MissingPerson.id.desc()
        )
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


@app.get("/missing_people/search", response_model=MissingPerson)
def search_missing_person(
    name: Annotated[str, Query(min_length=1, max_length=200)],
    session: Annotated[Session, Depends(get_session)],
) -> MissingPerson:
    person = find_missing_person_by_name(session, name)
    if person is None:
        raise HTTPException(status_code=404, detail="Missing person not found")
    return person


@app.get("/missing_people/{person_id}", response_model=MissingPerson)
def get_missing_person(
    person_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> MissingPerson:
    person = session.get(MissingPerson, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Missing person not found")
    return person


@app.get(
    "/sync/missing_people/status",
    response_model=list[SyncState],
    dependencies=[Depends(require_private_token)],
)
def missing_people_sync_status(
    session: Annotated[Session, Depends(get_session)],
) -> list[SyncState]:
    return list(session.exec(select(SyncState).order_by(SyncState.source)).all())
