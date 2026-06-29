"""Webhook endpoints for the bot's "Motor Conversacional" output.

Each route corresponds to one ``accion`` emitted by the n8n Switch node described
in ``Bot_salva_vidas.md`` (§9). In n8n, add a Switch on ``{{ $json.accion }}``
with one HTTP Request per branch pointing to the matching route below.
"""

from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.adapters.green_api import Notifier, get_notifier
from app.config import Settings, get_settings
from app.database import get_session
from app.face import FaceMatcher, get_face_matcher
from app.models import MissingPerson
from app.services import bot_intake
from app.services.search import find_missing_person_by_cedula
from app.utils.images import download_image

router = APIRouter(prefix="/bot", tags=["bot"])


# ---------------------------------------------------------------------------
# Shared dependencies
# ---------------------------------------------------------------------------


@lru_cache
def _cached_face_matcher() -> FaceMatcher:
    # Cache so the (potentially heavy) model loads once per process.
    return get_face_matcher(get_settings())


def get_face_matcher_dependency() -> FaceMatcher:
    return _cached_face_matcher()


def get_notifier_dependency(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Notifier:
    return get_notifier(settings)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class BotContext(BaseModel):
    """Common fields sent by the bot on every request."""

    datos: dict[str, Any] = Field(default_factory=dict)
    imagen_ref: str | None = None
    chat_id: str | None = None
    canal: str = "whatsapp"
    sender: str | None = None
    nombre: str | None = None
    messages: Any | None = None


class RegisterResponse(BaseModel):
    ok: bool = True
    report_id: int


class SearchByPhotoResponse(BaseModel):
    found: bool


class SearchByNameResponse(BaseModel):
    found: bool
    person: MissingPerson | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/registrar",
    response_model=RegisterResponse,
    summary="Register a missing person reported through the bot",
)
def registrar_persona(
    payload: BotContext,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dependency)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RegisterResponse:
    """Download the photo, compute its face embedding and persist the report.

    Creates both a ``missing_people`` row (so the person is searchable through
    the existing endpoints) and a linked ``bot_reports`` row that holds the
    bot-specific data (age, description, contact, conversation snapshot and
    face embedding).
    """
    chat_id = payload.chat_id or payload.sender or ""
    report = bot_intake.register_missing_person(
        session,
        matcher,
        settings,
        datos=payload.datos,
        imagen_ref=payload.imagen_ref,
        chat_id=chat_id,
        channel=payload.canal,
        sender=payload.sender,
        reporter_name=payload.nombre,
        conversation=payload.messages,
    )
    return RegisterResponse(report_id=report.id)


@router.post(
    "/buscar-foto",
    response_model=SearchByPhotoResponse,
    summary="Search for a missing person by photo (facial recognition)",
)
def buscar_por_foto(
    payload: BotContext,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dependency)],
    notifier: Annotated[Notifier, Depends(get_notifier_dependency)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchByPhotoResponse:
    """Compare the uploaded photo against all registered missing-person embeddings.

    If a match is found above the configured threshold, the original reporter is
    notified via WhatsApp (Green API) and ``{"found": true}`` is returned. The
    matched report is only marked as found by the explicit confirmation flow.

    If no match is found, returns ``{"found": false}`` with no person data
    (by design: we do not expose any personal information on a miss).
    """
    chat_id = payload.chat_id or payload.sender or ""
    match = bot_intake.search_by_photo(
        session,
        matcher,
        notifier,
        settings,
        datos=payload.datos,
        imagen_ref=payload.imagen_ref,
        searcher_chat_id=chat_id,
        searcher_contact=payload.datos.get("contacto") or payload.sender,
    )
    return SearchByPhotoResponse(found=match is not None)


@router.post(
    "/buscar-nombre",
    response_model=SearchByNameResponse,
    summary="Search for a missing person by name",
)
def buscar_por_nombre(
    payload: BotContext,
    session: Annotated[Session, Depends(get_session)],
) -> SearchByNameResponse:
    """Search the database by name using multi-strategy matching (exact → all
    tokens → any token).

    The ``query`` field inside ``datos`` is used as the search term; falls back
    to ``datos.nombre`` if ``query`` is absent.
    """
    name = payload.datos.get("query") or payload.datos.get("nombre") or ""
    person = bot_intake.search_by_name(session, name) if name else None
    return SearchByNameResponse(found=person is not None, person=person)


@router.post(
    "/buscar-cedula-foto",
    response_model=SearchByNameResponse,
    summary="Search for a missing person by OCR on a cedula photo",
)
def buscar_por_cedula_foto(
    payload: BotContext,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchByNameResponse:
    """Recibe una foto de cedula (via URL en ``imagen_ref``), extrae nombre y
    cedula, y busca en la base de datos.

    Busca primero por cedula. Si no encuentra, busca por nombre.
    """
    ocr_nombre: str | None = None
    ocr_cedula: str | None = None

    if payload.imagen_ref:
        try:
            image_bytes = download_image(
                payload.imagen_ref, timeout=settings.image_download_timeout_seconds
            )
            from app.services.ocr_service import extract_from_id_image

            data = extract_from_id_image(image_bytes)
            ocr_nombre = data.get("nombre")
            ocr_cedula = data.get("cedula")
        except ImportError:
            pass
        except Exception:
            pass

    # Buscar: primero por cedula, luego por nombre
    person: MissingPerson | None = None
    if ocr_cedula:
        person = find_missing_person_by_cedula(session, ocr_cedula)
    if not person and ocr_nombre:
        person = bot_intake.search_by_name(session, ocr_nombre)

    return SearchByNameResponse(found=person is not None, person=person)
