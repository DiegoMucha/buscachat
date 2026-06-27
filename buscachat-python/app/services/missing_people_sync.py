from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session

from app.adapters.base import MissingPeopleAdapter, MissingPersonPayload
from app.models import MissingPerson, SourceRecord, SyncState, utc_now


@dataclass(frozen=True)
class SyncResult:
    source: str
    records_seen: int
    records_upserted: int
    last_source_date: datetime | None


def sync_missing_people(
    *,
    session: Session,
    adapter: MissingPeopleAdapter,
    page_limit: int,
    max_pages: int | None = None,
) -> SyncResult:
    records_seen = 0
    records_upserted = 0
    last_source_date: datetime | None = None
    offset = 0
    pages_seen = 0

    try:
        while True:
            if max_pages is not None and pages_seen >= max_pages:
                break

            page = adapter.fetch_page(offset=offset, limit=page_limit)
            pages_seen += 1
            if not page:
                break

            for record in page:
                records_seen += 1
                records_upserted += _upsert_record(session, record)
                if record.source_date and (
                    last_source_date is None or record.source_date > last_source_date
                ):
                    last_source_date = record.source_date

            session.commit()

            if len(page) < page_limit:
                break
            offset += page_limit

        _upsert_sync_state(
            session,
            source=adapter.source,
            last_source_date=last_source_date,
            records_seen=records_seen,
            records_upserted=records_upserted,
            last_error=None,
            success=True,
        )
        session.commit()
        return SyncResult(
            source=adapter.source,
            records_seen=records_seen,
            records_upserted=records_upserted,
            last_source_date=last_source_date,
        )
    except Exception as exc:
        session.rollback()
        _upsert_sync_state(
            session,
            source=adapter.source,
            last_source_date=last_source_date,
            records_seen=records_seen,
            records_upserted=records_upserted,
            last_error=str(exc)[:2000],
            success=False,
        )
        session.commit()
        raise


def _upsert_record(session: Session, record: MissingPersonPayload) -> int:
    now = utc_now()
    person_values = {
        "source": record.source,
        "external_id": record.external_id,
        "full_name": record.full_name,
        "status": record.status,
        "raw_status": record.raw_status,
        "cedula_masked": record.cedula_masked,
        "municipio": record.municipio,
        "parroquia": record.parroquia,
        "hospital_name": record.hospital_name,
        "last_known_location": record.last_known_location,
        "photo_url": record.photo_url,
        "source_date": record.source_date,
        "created_at": now,
        "updated_at": now,
    }
    person_insert = insert(MissingPerson.__table__).values(**person_values)
    session.exec(
        person_insert.on_conflict_do_update(
            constraint="uq_missing_people_source_external",
            set_={
                key: person_insert.excluded[key]
                for key in person_values
                if key not in {"source", "external_id", "created_at"}
            },
        )
    )

    source_values = {
        "source": record.source,
        "external_id": record.external_id,
        "raw_payload": record.raw_payload,
        "source_date": record.source_date,
        "synced_at": now,
    }
    source_insert = insert(SourceRecord.__table__).values(**source_values)
    session.exec(
        source_insert.on_conflict_do_update(
            constraint="uq_source_records_source_external",
            set_={
                "raw_payload": source_insert.excluded.raw_payload,
                "source_date": source_insert.excluded.source_date,
                "synced_at": source_insert.excluded.synced_at,
            },
        )
    )
    return 1


def _upsert_sync_state(
    session: Session,
    *,
    source: str,
    last_source_date: datetime | None,
    records_seen: int,
    records_upserted: int,
    last_error: str | None,
    success: bool,
) -> None:
    now = utc_now()
    values = {
        "source": source,
        "last_success_at": now if success else None,
        "last_source_date": last_source_date,
        "last_records_seen": records_seen,
        "last_records_upserted": records_upserted,
        "last_error": last_error,
        "updated_at": now,
    }
    state_insert = insert(SyncState.__table__).values(**values)

    update_values = {
        "last_records_seen": state_insert.excluded.last_records_seen,
        "last_records_upserted": state_insert.excluded.last_records_upserted,
        "last_error": state_insert.excluded.last_error,
        "updated_at": state_insert.excluded.updated_at,
    }
    if success:
        update_values["last_success_at"] = state_insert.excluded.last_success_at
        update_values["last_source_date"] = state_insert.excluded.last_source_date

    session.exec(
        state_insert.on_conflict_do_update(
            index_elements=["source"],
            set_=update_values,
        )
    )
