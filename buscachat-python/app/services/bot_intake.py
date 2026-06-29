"""Intake logic for the conversational bot (WhatsApp/Telegram).

Wires the ``accion`` emitted by the n8n "Motor Conversacional" to real database
work: registering a missing person (with a face embedding), searching by photo
(facial recognition) and searching by name.

Functions are pure: they receive the session, the face matcher and the notifier,
mirroring the style of ``missing_people_sync``. The bot's ``datos`` keys stay in
Spanish because that is the contract produced by the n8n flow.
"""

import logging
import uuid
from collections.abc import Mapping
from typing import Any

from sqlmodel import Session, select

from app.adapters.green_api import Notifier
from app.config import Settings
from app.face.base import FaceMatcher, cosine_similarity
from app.models import BotReport, MissingPerson, utc_now
from app.services.search import find_missing_people_by_name, find_missing_person_by_name
from app.utils.images import download_image

log = logging.getLogger(__name__)


def _photo_ref(datos: Mapping[str, Any], imagen_ref: str | None) -> str | None:
    return imagen_ref or datos.get("foto_ref") or datos.get("foto") or None


def _embed_from_url(matcher: FaceMatcher, url: str | None, *, timeout: float) -> list[float] | None:
    if not url:
        return None
    try:
        image_bytes = download_image(url, timeout=timeout)
    except Exception:
        log.exception("Failed to download image from %s", url)
        return None
    return matcher.embed(image_bytes)


def register_missing_person(
    session: Session,
    matcher: FaceMatcher,
    settings: Settings,
    *,
    datos: Mapping[str, Any],
    imagen_ref: str | None,
    chat_id: str,
    channel: str,
    sender: str | None = None,
    reporter_name: str | None = None,
    conversation: Any | None = None,
    face_embedding: list[float] | None = None,
) -> BotReport:
    """Register a missing person reported through the bot.

    Downloads the photo, computes its face embedding, inserts a ``MissingPerson``
    row (so it stays searchable through the existing endpoints) and a linked
    ``BotReport`` holding the bot-specific data, contact and conversation.
    """
    full_name = (datos.get("nombre") or "").strip() or "Desconocido"
    location = datos.get("ubicacion")
    photo_url = _photo_ref(datos, imagen_ref)
    embedding = face_embedding
    if embedding is None:
        embedding = _embed_from_url(matcher, photo_url, timeout=settings.image_download_timeout_seconds)

    external_id = uuid.uuid4().hex
    person = MissingPerson(
        source=settings.bot_source,
        external_id=external_id,
        full_name=full_name,
        status="missing",
        cedula_masked=datos.get("cedula"),
        last_known_location=location,
        photo_url=photo_url,
        source_date=utc_now(),
    )
    session.add(person)
    session.flush()  # assign person.id

    report = BotReport(
        missing_person_id=person.id,
        channel=channel,
        chat_id=chat_id,
        sender=sender,
        reporter_name=reporter_name,
        contact=datos.get("contacto"),
        full_name=full_name,
        age=str(datos["edad"]) if datos.get("edad") is not None else None,
        description=datos.get("descripcion"),
        location=location,
        photo_url=photo_url,
        face_embedding=embedding,
        status="missing",
        conversation=conversation,
        datos_raw=dict(datos),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def search_by_photo(
    session: Session,
    matcher: FaceMatcher,
    notifier: Notifier,
    settings: Settings,
    *,
    datos: Mapping[str, Any],
    imagen_ref: str | None,
    searcher_chat_id: str | None = None,
    searcher_contact: str | None = None,
    query_embedding: list[float] | None = None,
) -> BotReport | None:
    """Search registered reports by face.

    If a registered (``missing``) report matches the uploaded photo above the
    configured threshold, notify the original reporter and return the matched
    report. The status is not changed automatically; callers should use
    ``mark_missing_person_found`` after the searcher explicitly confirms.
    """
    photo_url = _photo_ref(datos, imagen_ref)
    if query_embedding is None:
        query_embedding = _embed_from_url(matcher, photo_url, timeout=settings.image_download_timeout_seconds)
    if query_embedding is None:
        return None

    best_report = session.exec(
        select(BotReport)
        .where(BotReport.status == "missing")
        .where(BotReport.face_embedding.is_not(None))
        .order_by(BotReport.face_embedding.cosine_distance(query_embedding))
        .limit(1)
    ).first()
    if best_report is None:
        return None

    if cosine_similarity(query_embedding, list(best_report.face_embedding)) < settings.face_match_threshold:
        return None

    _notify_reporter(notifier, best_report, searcher_contact or datos.get("contacto"))
    session.commit()
    session.refresh(best_report)
    return best_report


def _notify_reporter(notifier: Notifier, report: BotReport, searcher_contact: str | None) -> None:
    """Notify the original reporter that their person was found."""
    if report.channel != "whatsapp":
        log.info(
            "Skipping notification for channel %s (report %s)",
            report.channel,
            report.id,
        )
        return

    message = f"¡Buenas noticias! {report.full_name} fue reportada como encontrada."
    if searcher_contact:
        message += f"\nContacto de quien la encontró: {searcher_contact}"

    try:
        notifier.send_text(report.chat_id, message)
        report.notified_at = utc_now()
    except Exception:
        log.exception("Failed to notify reporter for report %s", report.id)


def search_by_name(session: Session, name: str) -> MissingPerson | None:
    """Search the database by name (reuses the existing search service)."""
    return find_missing_person_by_name(session, name)


def search_by_name_matches(
    session: Session,
    name: str,
    *,
    limit: int = 10,
) -> list[MissingPerson]:
    """Search the database by name and return up to ``limit`` matches."""
    return find_missing_people_by_name(session, name, limit=limit)


def mark_missing_person_found(session: Session, person_id: int) -> MissingPerson | None:
    person = session.get(MissingPerson, person_id)
    if person is None:
        return None

    now = utc_now()
    if person.status != "found":
        person.status = "found"
        person.updated_at = now
        session.add(person)

    linked_reports = session.exec(select(BotReport).where(BotReport.missing_person_id == person_id)).all()
    for report in linked_reports:
        if report.status != "found":
            report.status = "found"
            report.found_at = now
            report.updated_at = now
            session.add(report)

    session.commit()
    session.refresh(person)
    return person
