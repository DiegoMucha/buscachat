from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select
from testcontainers.postgres import PostgresContainer

from app.config import Settings
from app.database import run_migrations
from app.face import StubFaceMatcher
from app.models import BotReport, MissingPerson
from app.services import bot_intake
from app.services.search import find_missing_person_by_name


pytestmark = pytest.mark.e2e


class SpyNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send_text(self, chat_id: str, message: str) -> None:
        self.calls.append((chat_id, message))


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg18") as postgres:
        yield postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )


def test_register_and_search_by_photo(postgres_url: str, monkeypatch) -> None:
    engine = create_engine(postgres_url, pool_pre_ping=True)
    run_migrations(engine)

    settings = Settings(face_matcher="stub", notifier="null")
    matcher = StubFaceMatcher()
    notifier = SpyNotifier()

    # The stub embeds raw bytes; make download_image return URL-derived bytes so
    # the same imagen_ref yields the same embedding (similarity 1.0).
    monkeypatch.setattr(
        bot_intake, "download_image", lambda url, timeout=30.0: url.encode()
    )

    with Session(engine) as session:
        report = bot_intake.register_missing_person(
            session,
            matcher,
            settings,
            datos={
                "nombre": "Maria Fernandez",
                "edad": "34",
                "ubicacion": "Catia La Mar",
                "descripcion": "Camisa azul",
                "contacto": "+58 412 0000000",
            },
            imagen_ref="https://example.test/maria.jpg",
            chat_id="58412111@c.us",
            channel="whatsapp",
            sender="58412111",
            reporter_name="Reporter",
            conversation=[{"role": "user", "text": "hola"}],
        )

        assert report.id is not None
        assert report.missing_person_id is not None
        assert report.face_embedding is not None
        assert report.status == "missing"

        person = session.get(MissingPerson, report.missing_person_id)
        assert person is not None
        assert person.source == settings.bot_source
        assert person.status == "missing"
        assert find_missing_person_by_name(session, "Maria Fernandez") == person

    # Search with a non-matching photo -> nothing.
    with Session(engine) as session:
        no_match = bot_intake.search_by_photo(
            session,
            matcher,
            notifier,
            settings,
            datos={},
            imagen_ref="https://example.test/someone-else.jpg",
        )
        assert no_match is None
        assert notifier.calls == []

    # Search with the matching photo -> found + reporter notified.
    with Session(engine) as session:
        match = bot_intake.search_by_photo(
            session,
            matcher,
            notifier,
            settings,
            datos={"contacto": "+58 414 9999999"},
            imagen_ref="https://example.test/maria.jpg",
        )
        assert match is not None
        assert match.status == "found"
        assert match.found_at is not None
        assert match.notified_at is not None

        person = session.get(MissingPerson, match.missing_person_id)
        assert person is not None
        assert person.status == "found"

    assert len(notifier.calls) == 1
    chat_id, message = notifier.calls[0]
    assert chat_id == "58412111@c.us"
    assert "Maria Fernandez" in message
    assert "+58 414 9999999" in message
