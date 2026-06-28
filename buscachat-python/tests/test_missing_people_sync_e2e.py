from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select
from testcontainers.postgres import PostgresContainer

from app.adapters.base import MissingPersonPayload
from app.database import run_migrations
from app.models import MissingPerson, SourceRecord, SyncState
from app.services import sync_missing_people
from app.services.search import find_missing_person_by_name


pytestmark = pytest.mark.e2e


class FakeMissingPeopleAdapter:
    source = "test-source"

    def __init__(self, pages: list[list[MissingPersonPayload]]) -> None:
        self.pages = pages

    def fetch_page(self, *, offset: int, limit: int) -> list[MissingPersonPayload]:
        page_index = offset // limit
        if page_index >= len(self.pages):
            return []
        return self.pages[page_index]


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg18") as postgres:
        yield postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+psycopg://")


def test_missing_people_sync_runs_migrations_and_upserts(postgres_url: str) -> None:
    engine = create_engine(postgres_url, pool_pre_ping=True)
    run_migrations(engine)

    first_seen = datetime(2026, 6, 27, 18, 0, tzinfo=UTC)
    updated_seen = datetime(2026, 6, 27, 19, 0, tzinfo=UTC)

    first_adapter = FakeMissingPeopleAdapter(
        [
            [
                MissingPersonPayload(
                    source="test-source",
                    external_id="person-1",
                    full_name="Maria Fernandez",
                    status="missing",
                    raw_status="seeking_info",
                    last_known_location="Catia La Mar",
                    source_date=first_seen,
                    raw_payload={"id": "person-1", "display_name": "Maria Fernandez"},
                ),
                MissingPersonPayload(
                    source="test-source",
                    external_id="person-2",
                    full_name="Jose Perez",
                    status="found",
                    raw_status="found_alive",
                    last_known_location="La Guaira",
                    source_date=first_seen,
                    raw_payload={"id": "person-2", "display_name": "Jose Perez"},
                ),
            ],
            [],
        ]
    )

    with Session(engine) as session:
        result = sync_missing_people(
            session=session,
            adapter=first_adapter,
            page_limit=2,
        )
        assert result.records_seen == 2
        assert result.records_upserted == 2

    second_adapter = FakeMissingPeopleAdapter(
        [
            [
                MissingPersonPayload(
                    source="test-source",
                    external_id="person-1",
                    full_name="Maria Fernandez",
                    status="found",
                    raw_status="found_alive",
                    last_known_location="Catia La Mar",
                    source_date=updated_seen,
                    raw_payload={"id": "person-1", "display_name": "Maria Fernandez"},
                )
            ],
            [],
        ]
    )

    with Session(engine) as session:
        result = sync_missing_people(
            session=session,
            adapter=second_adapter,
            page_limit=1,
        )
        assert result.records_seen == 1

        people = session.exec(select(MissingPerson)).all()
        source_records = session.exec(select(SourceRecord)).all()
        sync_state = session.get(SyncState, "test-source")

        assert len(people) == 2
        assert len(source_records) == 2
        assert sync_state is not None
        assert sync_state.last_records_seen == 1
        assert sync_state.last_error is None

        person_1 = session.exec(
            select(MissingPerson).where(MissingPerson.external_id == "person-1")
        ).one()
        assert person_1.status == "found"
        assert person_1.source_date == updated_seen

        assert find_missing_person_by_name(session, "Maria Fernandez") == person_1
        assert find_missing_person_by_name(session, "Maria") == person_1
        assert find_missing_person_by_name(session, "No Existe") is None
