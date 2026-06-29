"""Genera embeddings faciales para registros sincronizados que tienen photo_url.

Los registros de SOS Venezuela traen photo_url pero nunca se les genera embedding.
Este módulo procesa las fotos pendientes y crea BotReport con los embeddings.
"""

import logging
from collections.abc import Iterator

from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.database import engine
from app.face import FaceMatcher, get_face_matcher
from app.models import BotReport, MissingPerson, utc_now
from app.utils.images import download_image

log = logging.getLogger(__name__)


def generate_embeddings_for_synced_records(
    *,
    settings: Settings | None = None,
    max_records: int | None = 50,
    timeout: float = 30.0,
) -> dict:
    """Busca MissingPersons con foto sin BotReport y les genera embedding facial.

    Args:
        settings: Configuración (usa get_settings() si no se pasa).
        max_records: Máximo de registros a procesar (None = todos).
        timeout: Timeout por descarga de imagen.

    Returns:
        Dict con {processed, successes, failures, skipped}.
    """
    if settings is None:
        settings = get_settings()

    matcher: FaceMatcher = get_face_matcher(settings)

    with Session(engine) as session:
        # Buscar MissingPersons con foto pero sin BotReport vinculado
        # que tenga embedding
        photos = _find_pending_photos(session, max_records)

        processed = 0
        successes = 0
        failures = 0
        skipped = 0

        for person in photos:
            processed += 1
            if not person.photo_url:
                skipped += 1
                continue

            try:
                log.info("Downloading photo for %s (ID=%s)", person.full_name, person.id)
                image_bytes = download_image(person.photo_url, timeout=timeout)
                embedding = matcher.embed(image_bytes)

                if embedding is None:
                    log.warning("No face detected in photo for %s", person.full_name)
                    skipped += 1
                    continue

                # Crear BotReport vinculado con el embedding
                report = BotReport(
                    missing_person_id=person.id,
                    channel="sosvenezuela2026",
                    chat_id=f"sync-{person.id}",
                    sender="sync",
                    reporter_name="SOS Venezuela Sync",
                    contact=None,
                    full_name=person.full_name,
                    age=None,
                    description=None,
                    location=person.last_known_location,
                    photo_url=person.photo_url,
                    face_embedding=list(embedding),
                    status=person.status,
                    datos_raw={"synced_from": "sosvenezuela2026"},
                )
                session.add(report)
                session.commit()

                log.info("Embedding generated for %s (report %s)", person.full_name, report.id)
                successes += 1

            except Exception:
                log.exception("Failed to generate embedding for %s (ID=%s)", person.full_name, person.id)
                session.rollback()
                failures += 1

    return {
        "processed": processed,
        "successes": successes,
        "failures": failures,
        "skipped": skipped,
    }


def _find_pending_photos(session: Session, max_records: int | None = None) -> Iterator[MissingPerson]:
    """Encuentra MissingPersons con photo_url que no tienen BotReport con embedding."""
    # Subquery: IDs de MissingPersons que YA tienen BotReport con embedding
    with_embedding = (
        select(BotReport.missing_person_id)
        .where(BotReport.face_embedding.is_not(None))
        .subquery()
    )

    query = (
        select(MissingPerson)
        .where(MissingPerson.photo_url.is_not(None))
        .where(MissingPerson.id.not_in(with_embedding))
        .order_by(MissingPerson.id.desc())
    )

    if max_records is not None:
        query = query.limit(max_records)

    return iter(session.exec(query).all())
