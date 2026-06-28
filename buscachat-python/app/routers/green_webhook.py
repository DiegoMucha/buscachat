"""Webhook de Green API — recibe mensajes de WhatsApp vía Green API."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.config import Settings, get_settings
from app.database import get_session
from app.face import FaceMatcher
from app.routers.whatsapp_base import (
    get_face_matcher_dep,
    get_notifier_dep,
    run_conversation_motor,
)
from app.services import bot_intake
from app.adapters.green_api import Notifier

log = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp-webhook"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class WebhookResponse(BaseModel):
    chat_id: str
    text: str
    accion: str | None = None


# ---------------------------------------------------------------------------
# Extraer mensaje de Green API
# ---------------------------------------------------------------------------


def _extract_green_message(body: dict) -> dict:
    md = body.get("messageData") or {}
    sd = body.get("senderData") or {}

    is_image = md.get("typeMessage") == "imageMessage"
    text = ""
    imagen_ref = None

    if is_image:
        text = md.get("caption") or ""
        if md.get("fileMessageData"):
            imagen_ref = md["fileMessageData"].get("downloadUrl")
    elif md.get("textMessageData"):
        text = md["textMessageData"].get("textMessage", "")

    raw_sender = sd.get("sender", "")
    chat_id = raw_sender if "@" in raw_sender else f"{raw_sender}@c.us"

    return {
        "canal": "whatsapp",
        "tipo": "imagen" if is_image else "texto",
        "text": text.strip(),
        "imagen_ref": imagen_ref,
        "chat_id": chat_id,
        "sender": raw_sender,
        "nombre": sd.get("senderName") or "",
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/webhook")
def green_webhook(
    body: dict,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dep)],
    notifier: Annotated[Notifier, Depends(get_notifier_dep)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebhookResponse:
    msg = _extract_green_message(body)
    log.info("Green webhook: chat=%s tipo=%s text=%s", msg["chat_id"], msg["tipo"], msg["text"][:50])

    result = run_conversation_motor(msg)

    if result.get("accion") is None:
        return WebhookResponse(
            chat_id=result["chat_id"],
            text=result.get("respuesta", "Listo."),
        )

    accion = result["accion"]
    chat_id = result["chat_id"]
    datos = result.get("datos", {})
    sender = result.get("sender", "")

    if accion == "registrar_persona":
        report = bot_intake.register_missing_person(
            session, matcher, settings,
            datos=datos,
            imagen_ref=result.get("imagen_ref"),
            chat_id=chat_id,
            channel=result.get("canal", "whatsapp"),
            sender=sender,
            reporter_name=result.get("nombre"),
        )
        return WebhookResponse(chat_id=chat_id, text=f"✅ Registro creado (ID: {report.id}).", accion=accion)

    if accion == "buscar_por_foto":
        match = bot_intake.search_by_photo(
            session, matcher, notifier, settings,
            datos=datos,
            imagen_ref=result.get("imagen_ref"),
            searcher_chat_id=chat_id,
            searcher_contact=datos.get("contacto") or sender,
        )
        if match:
            return WebhookResponse(chat_id=chat_id, text=_format_match_info(match), accion=accion)
        return WebhookResponse(chat_id=chat_id, text="❌ No se encontró match facial.", accion=accion)

    if accion == "buscar_por_nombre":
        name = datos.get("query", "")
        person = bot_intake.search_by_name(session, name) if name else None
        if person:
            extra = ""
            if person.cedula_masked:
                extra += f"\nCédula: {person.cedula_masked}"
            if person.last_known_location:
                extra += f"\nUbicación: {person.last_known_location}"
            return WebhookResponse(chat_id=chat_id, text=f"✅ *{person.full_name}*\nEstado: {person.status}{extra}", accion=accion)
        return WebhookResponse(chat_id=chat_id, text=f"❌ No se encontró a *{name}*.", accion=accion)

    return WebhookResponse(chat_id=chat_id, text="Listo.")


def _format_match_info(report) -> str:
    parts = [f"✅ *{report.full_name}*"]
    if getattr(report, "age", None):
        parts.append(f"👤 Edad: {report.age}")
    if getattr(report, "description", None):
        parts.append(f"📝 Descripción: {report.description}")
    if getattr(report, "location", None):
        parts.append(f"📍 Ubicación: {report.location}")
    if getattr(report, "contact", None):
        parts.append(f"📞 Contacto: {report.contact}")
    parts.append(f"📊 Estado: {report.status}")
    return "\n".join(parts)
