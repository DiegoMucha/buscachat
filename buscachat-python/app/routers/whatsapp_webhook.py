"""Webhook directo de Green API — sin n8n.

Recibe el payload de Green API, ejecuta el motor conversacional interno y
despacha a los servicios de bot_intake cuando el flujo emite una acción.

Estado de conversación: diccionario en memoria (reinicia al reiniciar el server).
"""

import logging
import threading
from functools import lru_cache
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlmodel import Session

from app.adapters.green_api import Notifier, get_notifier
from app.config import Settings, get_settings
from app.database import get_session
from app.face import FaceMatcher, get_face_matcher
from app.face.base import cosine_similarity
from app.services import bot_intake

log = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp-webhook"])

# ---------------------------------------------------------------------------
# Dependencias cacheadas (igual que en bot.py)
# ---------------------------------------------------------------------------


@lru_cache
def _cached_face_matcher() -> FaceMatcher:
    return get_face_matcher(get_settings())


def _get_face_matcher() -> FaceMatcher:
    return _cached_face_matcher()


def _get_notifier(settings: Annotated[Settings, Depends(get_settings)]) -> Notifier:
    return get_notifier(settings)


# ---------------------------------------------------------------------------
# Estado conversacional en memoria (chat_id → { paso, datos })
# ---------------------------------------------------------------------------
_state: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _get_state(chat_id: str) -> dict[str, Any]:
    with _lock:
        if chat_id not in _state:
            _state[chat_id] = {"paso": "menu"}
        return _state[chat_id]


def _set_state(chat_id: str, data: dict[str, Any] | None) -> None:
    with _lock:
        if data is None:
            _state.pop(chat_id, None)
        else:
            _state[chat_id] = data


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GreenAPIMessageData(BaseModel):
    typeMessage: str = "textMessage"
    textMessageData: dict[str, Any] | None = None
    caption: str | None = None
    fileMessageData: dict[str, Any] | None = None


class GreenAPISenderData(BaseModel):
    sender: str = ""
    senderName: str | None = None


class GreenAPIWebhook(BaseModel):
    """Payload que Green API envía al webhook."""

    messageData: GreenAPIMessageData | None = None
    senderData: GreenAPISenderData | None = None


class WebhookResponse(BaseModel):
    """Respuesta formateada para que Green API la reenvíe al usuario."""

    chat_id: str
    text: str
    accion: str | None = None


# ---------------------------------------------------------------------------
# Extraer mensaje normalizado
# ---------------------------------------------------------------------------


def _extract_message(body: GreenAPIWebhook) -> dict[str, Any]:
    md = body.messageData or GreenAPIMessageData()
    sd = body.senderData or GreenAPISenderData()

    is_image = md.typeMessage == "imageMessage"
    text = ""
    imagen_ref = None

    if is_image:
        text = md.caption or ""
        if md.fileMessageData:
            imagen_ref = md.fileMessageData.get("downloadUrl")
    elif md.textMessageData:
        text = md.textMessageData.get("textMessage", "")

    raw_sender = sd.sender or ""
    chat_id = raw_sender if "@" in raw_sender else f"{raw_sender}@c.us"

    return {
        "canal": "whatsapp",
        "tipo": "imagen" if is_image else "texto",
        "text": text.strip(),
        "imagen_ref": imagen_ref,
        "chat_id": chat_id,
        "sender": raw_sender,
        "nombre": sd.senderName or "",
    }


# ---------------------------------------------------------------------------
# Motor conversacional
# ---------------------------------------------------------------------------


def _motor(msg: dict[str, Any]) -> dict[str, Any]:
    chat_id = msg["chat_id"]
    text = msg.get("text", "").strip().lower()

    # Comandos globales
    if text in ("menu", "0", "cancelar", "salir", "inicio"):
        _set_state(chat_id, {"paso": "menu"})
        return _menu_respuesta(chat_id, msg["canal"])

    state = _get_state(chat_id)
    paso = state.get("paso", "menu")

    # --- Menú ---
    if paso == "menu":
        return _handle_menu(msg, chat_id, text)

    # --- Buscar ---
    if paso == "buscar_modo":
        return _handle_buscar_modo(msg, chat_id, text)

    if paso == "buscar_foto":
        return _handle_buscar_foto(msg, chat_id)

    if paso == "buscar_nombre":
        return _handle_buscar_nombre(msg, chat_id, text)

    # --- Registrar ---
    if paso == "reg_nombre":
        return _handle_reg_nombre(msg, chat_id, text)
    if paso == "reg_contacto":
        return _handle_reg_contacto(msg, chat_id, text)
    if paso == "reg_confirmar":
        return _handle_reg_confirmar(msg, chat_id, text)

    return _menu_respuesta(chat_id, msg["canal"])


def _resp(chat_id: str, canal: str, text: str, accion: str | None = None) -> dict:
    return {"chat_id": chat_id, "canal": canal, "respuesta": text, "accion": accion}


def _menu_respuesta(chat_id: str, canal: str) -> dict:
    return _resp(
        chat_id,
        canal,
        "🤖 *BuscaChat*\n\n1️⃣ Buscar una persona\n2️⃣ Registrar una persona desaparecida\n3️⃣ Ayuda",
    )


def _handle_menu(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    if text == "1":
        _set_state(chat_id, {"paso": "buscar_modo"})
        return _resp(chat_id, canal, "¿Cómo querés buscar?\n\n1️⃣ Por foto\n2️⃣ Por nombre")
    if text == "2":
        _set_state(chat_id, {"paso": "reg_nombre"})
        return _resp(chat_id, canal, "Escribí el *nombre completo* de la persona desaparecida:")
    if text == "3":
        return _resp(
            chat_id,
            canal,
            "BuscaChat te ayuda a encontrar personas desaparecidas tras el terremoto. Escribí *menu* para volver al inicio.",
        )
    return _resp(chat_id, canal, "Respondé *1*, *2* o *3*")


def _handle_buscar_modo(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    if text == "1":
        _set_state(chat_id, {"paso": "buscar_foto"})
        return _resp(chat_id, canal, "Enviame la *foto* de la persona que buscás.")
    if text == "2":
        _set_state(chat_id, {"paso": "buscar_nombre"})
        return _resp(chat_id, canal, "Escribí el *nombre* de la persona que buscás:")
    return _resp(chat_id, canal, "Respondé *1* (foto) o *2* (nombre)")


def _handle_buscar_foto(msg: dict, chat_id: str) -> dict:
    _set_state(chat_id, None)
    return {
        "chat_id": chat_id,
        "canal": msg["canal"],
        "respuesta": None,
        "accion": "buscar_por_foto",
        "datos": {},
        "imagen_ref": msg.get("imagen_ref"),
        "sender": msg.get("sender"),
        "nombre": msg.get("nombre"),
    }


def _handle_buscar_nombre(msg: dict, chat_id: str, text: str) -> dict:
    _set_state(chat_id, None)
    return {
        "chat_id": chat_id,
        "canal": msg["canal"],
        "respuesta": None,
        "accion": "buscar_por_nombre",
        "datos": {"query": text},
        "sender": msg.get("sender"),
        "nombre": msg.get("nombre"),
    }


def _handle_reg_nombre(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    if not text:
        return _resp(chat_id, canal, "Por favor escribí un nombre válido.")
    _set_state(chat_id, {"paso": "reg_contacto", "nombre": msg.get("text", "").strip()})
    return _resp(
        chat_id,
        canal,
        f"¿Cómo se puede contactar a quien reporta a *{msg.get('text', '').strip()}*? (teléfono o nombre)",
    )


def _handle_reg_contacto(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    state = _get_state(chat_id)
    _set_state(
        chat_id,
        {"paso": "reg_confirmar", "nombre": state["nombre"], "contacto": text or ""},
    )
    return _resp(
        chat_id,
        canal,
        f"¿Confirmás el registro?\n\n*{state['nombre']}*\nContacto: {text or ''}\n\nRespondé *sí* para confirmar o *no* para cancelar.",
    )


def _handle_reg_confirmar(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    state = _get_state(chat_id)
    _set_state(chat_id, None)
    if text in ("si", "sí", "yes", "ok"):
        return {
            "chat_id": chat_id,
            "canal": canal,
            "respuesta": None,
            "accion": "registrar_persona",
            "datos": {"nombre": state["nombre"], "contacto": state["contacto"]},
            "sender": msg.get("sender"),
            "nombre": msg.get("nombre", state["nombre"]),
        }
    return _resp(chat_id, canal, "Registro cancelado. Escribí *menu* para empezar de nuevo.")


# ---------------------------------------------------------------------------
# Webhook principal
# ---------------------------------------------------------------------------


@router.post("/webhook")
def whatsapp_webhook(
    body: GreenAPIWebhook,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(_get_face_matcher)],
    notifier: Annotated[Notifier, Depends(_get_notifier)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebhookResponse:
    """Webhook que Green API llama cuando llega un mensaje de WhatsApp.

    Procesa la conversación internamente y despacha a los servicios de
    ``bot_intake`` cuando el flujo emite una acción.
    """
    # 1. Extraer mensaje normalizado
    msg = _extract_message(body)
    log.info("WhatsApp webhook: chat=%s tipo=%s text=%s", msg["chat_id"], msg["tipo"], msg["text"][:50])

    # 2. Motor conversacional
    result = _motor(msg)

    # 3. Si no hay acción, devolver respuesta conversacional
    if result.get("accion") is None:
        return WebhookResponse(
            chat_id=result["chat_id"],
            text=result.get("respuesta", "Listo."),
        )

    # 4. Ejecutar acción contra los servicios
    accion = result["accion"]
    chat_id = result["chat_id"]
    datos = result.get("datos", {})
    imagen_ref = result.get("imagen_ref")
    sender = result.get("sender", "")

    if accion == "registrar_persona":
        report = bot_intake.register_missing_person(
            session,
            matcher,
            settings,
            datos=datos,
            imagen_ref=imagen_ref,
            chat_id=chat_id,
            channel=result.get("canal", "whatsapp"),
            sender=sender,
            reporter_name=result.get("nombre"),
        )
        return WebhookResponse(
            chat_id=chat_id,
            text=f"✅ Registro creado (ID: {report.id}). Gracias por ayudar.",
            accion=accion,
        )

    if accion == "buscar_por_foto":
        match = bot_intake.search_by_photo(
            session,
            matcher,
            notifier,
            settings,
            datos=datos,
            imagen_ref=imagen_ref,
            searcher_chat_id=chat_id,
            searcher_contact=datos.get("contacto") or sender,
        )
        if match:
            return WebhookResponse(
                chat_id=chat_id,
                text="✅ ¡Match! Se encontró a la persona.",
                accion=accion,
            )
        return WebhookResponse(
            chat_id=chat_id,
            text="❌ No se encontró match facial en nuestros registros.",
            accion=accion,
        )

    if accion == "buscar_por_nombre":
        name = datos.get("query", "")
        person = bot_intake.search_by_name(session, name) if name else None
        if person:
            return WebhookResponse(
                chat_id=chat_id,
                text=f"✅ Encontrado: *{person.full_name}*\nEstado: {person.status}",
                accion=accion,
            )
        return WebhookResponse(
            chat_id=chat_id,
            text=f"❌ No se encontró a *{datos.get('query', '')}* en la base de datos.",
            accion=accion,
        )

    return WebhookResponse(chat_id=chat_id, text="Listo.")


# ---------------------------------------------------------------------------
# Meta WhatsApp Cloud API webhook
# ---------------------------------------------------------------------------


def _extract_meta_message(body: dict[str, Any]) -> dict[str, Any] | None:
    """Extrae el primer mensaje del payload de Meta WhatsApp Cloud API.

    Retorna ``None`` si no hay mensajes (ej. notificación de estado).
    """
    try:
        entry = (body.get("entry") or [{}])[0]
        change = (entry.get("changes") or [{}])[0]
        value = change.get("value") or {}
        messages = value.get("messages") or []
        contacts = value.get("contacts") or [{}]
        if not messages:
            return None
        msg = messages[0]
        contact = contacts[0]
    except (IndexError, KeyError, TypeError):
        return None

    msg_type = msg.get("type", "text")
    text = ""
    imagen_ref = None

    if msg_type == "text":
        text = (msg.get("text") or {}).get("body", "")
    elif msg_type == "image":
        text = (msg.get("image") or {}).get("caption", "")
        imagen_ref = (msg.get("image") or {}).get("id")  # media ID, no URL
    elif msg_type == "audio":
        text = "[audio]"
    elif msg_type == "document":
        text = "[documento]"

    wa_id = msg.get("from", "")
    chat_id = wa_id

    return {
        "canal": "whatsapp",
        "tipo": "imagen" if msg_type == "image" else "texto",
        "text": text.strip(),
        "imagen_ref": imagen_ref,  # Meta media ID (se resuelve después)
        "chat_id": chat_id,
        "sender": wa_id,
        "nombre": (contact.get("profile") or {}).get("name", ""),
    }


def _download_meta_image(media_id: str, access_token: str, *, timeout: float = 30.0) -> bytes | None:
    """Descarga una imagen de Meta usando su media ID."""
    try:
        with httpx.Client(timeout=timeout) as client:
            # 1. Obtener URL de descarga
            url_resp = client.get(
                f"https://graph.facebook.com/v19.0/{media_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            url_resp.raise_for_status()
            download_url = url_resp.json().get("url")
            if not download_url:
                return None

            # 2. Descargar bytes
            img_resp = client.get(
                download_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            img_resp.raise_for_status()
            return img_resp.content
    except Exception:
        log.exception("Failed to download Meta image %s", media_id)
        return None


@router.api_route("/meta-webhook", methods=["GET", "POST"])
async def meta_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(_get_face_matcher)],
    notifier: Annotated[Notifier, Depends(_get_notifier)],
    settings: Annotated[Settings, Depends(get_settings)],
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Webhook de Meta WhatsApp Cloud API.

    **GET**: verificación del webhook (Meta manda ``hub.mode=subscribe``).
    **POST**: mensaje entrante de WhatsApp.
    """
    # ── Verificación del webhook (GET) ──
    if request.method == "GET":
        if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
            log.info("Meta webhook verified successfully")
            return Response(content=str(hub_challenge or ""), media_type="text/plain")
        log.warning("Meta webhook verification failed: mode=%s token=%s", hub_mode, hub_verify_token)
        return Response(content="Verification failed", status_code=403)

    # ── Mensaje entrante (POST) ──
    body = await request.json()
    log.info("Meta webhook POST received")

    # Extraer mensaje normalizado
    msg = _extract_meta_message(body)
    if msg is None:
        log.info("Meta webhook: no message found (status notification or empty)")
        return Response(content="ok", media_type="text/plain")

    log.info("Meta webhook: chat=%s tipo=%s text=%s", msg["chat_id"], msg["tipo"], msg["text"][:50])

    # Si es imagen, descargar bytes y generar embedding ya
    if msg["tipo"] == "imagen" and msg["imagen_ref"] and settings.meta_access_token:
        image_bytes = _download_meta_image(
            msg["imagen_ref"], settings.meta_access_token,
            timeout=settings.image_download_timeout_seconds,
        )
        if image_bytes:
            msg["_image_bytes"] = image_bytes
            msg["_embedding"] = matcher.embed(image_bytes)
            log.info("Meta image downloaded and embedded: %s dims",
                     len(msg["_embedding"]) if msg["_embedding"] else 0)
        else:
            _send_meta_message(msg["chat_id"], "❌ No se pudo descargar la imagen. Intentá de nuevo.", settings)
            return Response(content="ok", media_type="text/plain")

    # Motor conversacional
    result = _motor(msg)

    # ── Respuesta conversacional (menú, preguntas) ──
    if result.get("accion") is None:
        text = result.get("respuesta", "Listo.")
        _send_meta_message(msg["chat_id"], text, settings)
        return Response(content="ok", media_type="text/plain")

    accion = result["accion"]
    chat_id = result["chat_id"]
    datos = result.get("datos", {})

    # ── REGISTRAR PERSONA ──
    if accion == "registrar_persona":
        embedding = msg.get("_embedding")
        if embedding:
            report = _meta_register_with_embedding(
                session, settings, result, datos, chat_id, embedding
            )
        else:
            report = bot_intake.register_missing_person(
                session, matcher, settings,
                datos=datos,
                imagen_ref=result.get("imagen_ref"),
                chat_id=chat_id,
                channel=result.get("canal", "whatsapp"),
                sender=result.get("sender", ""),
                reporter_name=result.get("nombre"),
            )
        _send_meta_message(chat_id, f"✅ Registro creado (ID: {report.id}). Gracias por ayudar.", settings)
        return Response(content="ok", media_type="text/plain")

    # ── BUSCAR POR FOTO ──
    if accion == "buscar_por_foto":
        query_embedding = msg.get("_embedding")
        if query_embedding is None:
            _send_meta_message(chat_id, "❌ No se detectó una cara en la foto.", settings)
            return Response(content="ok", media_type="text/plain")

        match = _meta_search_by_embedding(
            session, notifier, settings,
            query_embedding=query_embedding,
            searcher_chat_id=chat_id,
            searcher_contact=datos.get("contacto") or result.get("sender", ""),
        )
        if match:
            _send_meta_message(chat_id, "✅ ¡Match! Se encontró a la persona.", settings)
        else:
            _send_meta_message(chat_id, "❌ No se encontró match facial en nuestros registros.", settings)
        return Response(content="ok", media_type="text/plain")

    # ── BUSCAR POR NOMBRE ──
    if accion == "buscar_por_nombre":
        name = datos.get("query", "")
        person = bot_intake.search_by_name(session, name) if name else None
        if person:
            _send_meta_message(chat_id, f"✅ Encontrado: *{person.full_name}*\nEstado: {person.status}", settings)
        else:
            _send_meta_message(chat_id, f"❌ No se encontró a *{name}* en la base de datos.", settings)
        return Response(content="ok", media_type="text/plain")

    return Response(content="ok", media_type="text/plain")


def _send_meta_message(chat_id: str, text: str, settings: Settings) -> None:
    """Envía un mensaje de texto vía Meta WhatsApp Cloud API."""
    if not settings.meta_access_token or not settings.meta_phone_number_id:
        log.warning("Meta credentials missing; not sending: %s → %s", chat_id, text[:80])
        return

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"https://graph.facebook.com/v19.0/{settings.meta_phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {settings.meta_access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": chat_id,
                    "text": {"body": text},
                },
            )
            resp.raise_for_status()
            log.info("Meta message sent to %s", chat_id)
    except Exception:
        log.exception("Failed to send Meta message to %s", chat_id)


def _meta_register_with_embedding(
    session: Session,
    settings: Settings,
    result: dict[str, Any],
    datos: dict[str, Any],
    chat_id: str,
    embedding: list[float] | None,
) -> Any:
    """Registra una persona usando un embedding ya calculado."""
    import uuid
    from app.models import BotReport, MissingPerson, utc_now

    full_name = (datos.get("nombre") or "").strip() or "Desconocido"
    external_id = uuid.uuid4().hex
    person = MissingPerson(
        source=settings.bot_source,
        external_id=external_id,
        full_name=full_name,
        status="missing",
        last_known_location=datos.get("ubicacion"),
        source_date=utc_now(),
    )
    session.add(person)
    session.flush()

    report = BotReport(
        missing_person_id=person.id,
        channel=result.get("canal", "whatsapp"),
        chat_id=chat_id,
        sender=result.get("sender", ""),
        reporter_name=result.get("nombre"),
        contact=datos.get("contacto"),
        full_name=full_name,
        age=str(datos["edad"]) if datos.get("edad") is not None else None,
        description=datos.get("descripcion"),
        location=datos.get("ubicacion"),
        face_embedding=embedding,
        status="missing",
        datos_raw=dict(datos),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _meta_search_by_embedding(
    session: Session,
    notifier: Notifier,
    settings: Settings,
    *,
    query_embedding: list[float],
    searcher_chat_id: str | None = None,
    searcher_contact: str | None = None,
) -> Any | None:
    """Busca un match facial comparando el embedding contra bot_reports."""
    from sqlmodel import select
    from app.models import BotReport, MissingPerson, utc_now

    candidates = session.exec(
        select(BotReport).where(BotReport.status == "missing")
    ).all()

    best_report = None
    best_score = settings.face_match_threshold
    for candidate in candidates:
        if not candidate.face_embedding:
            continue
        score = cosine_similarity(query_embedding, candidate.face_embedding)
        if score >= best_score:
            best_score = score
            best_report = candidate

    if best_report is None:
        return None

    now = utc_now()
    best_report.status = "found"
    best_report.found_at = now
    best_report.updated_at = now
    session.add(best_report)

    if best_report.missing_person_id is not None:
        person = session.get(MissingPerson, best_report.missing_person_id)
        if person is not None:
            person.status = "found"
            person.updated_at = now
            session.add(person)

    # Notificar al reportante original via Green API (si está configurado)
    if best_report.channel == "whatsapp":
        message = f"¡Buenas noticias! {best_report.full_name} fue reportada como encontrada."
        if searcher_contact:
            message += f"\nContacto de quien la encontró: {searcher_contact}"
        try:
            notifier.send_text(best_report.chat_id, message)
            best_report.notified_at = now
        except Exception:
            log.exception("Failed to notify reporter for report %s", best_report.id)

    session.commit()
    session.refresh(best_report)
    return best_report
