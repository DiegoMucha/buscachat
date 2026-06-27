"""Webhook that receives the output of the bot's "Motor Conversacional".

A single endpoint (``POST /bot/chat``) dispatches on ``accion`` to the intake
service, matching the n8n Switch node described in ``Bot_salva_vidas.md`` (§9).
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
from app.models import BotReport, MissingPerson
from app.services import bot_intake

router = APIRouter(prefix="/bot", tags=["bot"])


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


class BotChatRequest(BaseModel):
    """Normalized item produced by the Motor Conversacional (see doc §4/§8)."""

    accion: str | None = None
    datos: dict[str, Any] = Field(default_factory=dict)
    imagen_ref: str | None = None
    chat_id: str | None = None
    canal: str = "whatsapp"
    sender: str | None = None
    nombre: str | None = None
    messages: Any | None = None


class BotChatResponse(BaseModel):
    ok: bool = True
    accion: str | None = None
    found: bool | None = None
    report_id: int | None = None
    person: MissingPerson | None = None


@router.post("/chat", response_model=BotChatResponse)
def bot_chat(
    payload: BotChatRequest,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dependency)],
    notifier: Annotated[Notifier, Depends(get_notifier_dependency)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BotChatResponse:
    chat_id = payload.chat_id or payload.sender or ""

    if payload.accion == "registrar_persona":
        report: BotReport = bot_intake.register_missing_person(
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
        return BotChatResponse(accion=payload.accion, report_id=report.id)

    if payload.accion == "buscar_por_foto":
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
        # No match -> return nothing about any person (per requirement).
        return BotChatResponse(accion=payload.accion, found=match is not None)

    if payload.accion == "buscar_por_nombre":
        name = payload.datos.get("query") or payload.datos.get("nombre") or ""
        person = bot_intake.search_by_name(session, name) if name else None
        return BotChatResponse(
            accion=payload.accion,
            found=person is not None,
            person=person,
        )

    # Unknown / null action: no-op.
    return BotChatResponse(accion=payload.accion)
