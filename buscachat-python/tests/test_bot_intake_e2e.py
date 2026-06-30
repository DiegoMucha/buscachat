from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session
from testcontainers.postgres import PostgresContainer

from app.config import Settings
from app.database import run_migrations
from app.face import StubFaceMatcher
from app.models import MissingPerson
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
        yield postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")


def test_register_and_search_by_photo(postgres_url: str, monkeypatch) -> None:
    engine = create_engine(postgres_url, pool_pre_ping=True)
    run_migrations(engine)

    settings = Settings(face_matcher="stub")
    matcher = StubFaceMatcher()
    notifier = SpyNotifier()

    # The stub embeds raw bytes; make download_image return URL-derived bytes so
    # the same imagen_ref yields the same embedding (similarity 1.0).
    monkeypatch.setattr(bot_intake, "download_image", lambda url, timeout=30.0: url.encode())

    with Session(engine) as session:
        report = bot_intake.register_missing_person(
            session,
            matcher,
            settings,
            datos={
                "nombre": "Alex Example Rivera",
                "edad": "34",
                "ubicacion": "Sample District",
                "descripcion": "Camisa azul",
                "contacto": "+15550101003",
            },
            imagen_ref="https://example.test/alex-example.jpg",
            chat_id="15551230000@c.us",
            channel="whatsapp",
            sender="15551230000",
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
        assert find_missing_person_by_name(session, "Alex Example Rivera") == person

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

    # Search with the matching photo -> returns a match + reporter notified.
    # The person is only marked found by the explicit confirmation action.
    with Session(engine) as session:
        match = bot_intake.search_by_photo(
            session,
            matcher,
            notifier,
            settings,
            datos={"contacto": "+15550101004"},
            imagen_ref="https://example.test/alex-example.jpg",
        )
        assert match is not None
        assert match.status == "missing"
        assert match.found_at is None
        assert match.notified_at is not None

        person = session.get(MissingPerson, match.missing_person_id)
        assert person is not None
        assert person.status == "missing"

        marked = bot_intake.mark_missing_person_found(session, person.id)
        assert marked is not None
        assert marked.status == "found"

    assert len(notifier.calls) == 1
    chat_id, message = notifier.calls[0]
    assert chat_id == "15551230000@c.us"
    assert "Alex Example Rivera" in message
    assert "+15550101004" in message
