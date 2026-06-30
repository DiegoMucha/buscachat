from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlmodel import Session

from app.config import get_settings
from app.database import get_session, run_migrations
from app.models import utc_now
from app.routers import web_chat as web_chat_router
from app.routers import whatsapp_meta_webhook as meta_webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
app.include_router(web_chat_router.router)
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
