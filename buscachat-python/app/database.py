from collections.abc import Generator
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlmodel import Session

from alembic import command
from app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIR = PROJECT_ROOT / "alembic"


def get_alembic_config() -> Config:
    config = Config(ALEMBIC_INI)
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def run_migrations(target_engine: Engine = engine) -> None:
    config = get_alembic_config()
    with target_engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
