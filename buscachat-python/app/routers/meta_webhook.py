"""Webhook de Meta WhatsApp Cloud API — recibe y responde mensajes vía Graph API."""

import logging
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlmodel import Session

from app.config import Settings, get_settings
from app.database import get_session
from app.face import FaceMatcher
from app.face.base import cosine_similarity
from app.routers.whatsapp_base import (
    get_face_matcher_dep,
    get_notifier_dep,
    run_conversation_motor,
    save_embedding_for_chat,
    set_conversation_state,
)
from app.services import bot_intake
from app.adapters.green_api import Notifier

log = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["meta-webhook"])


# ---------------------------------------------------------------------------
# Extraer mensaje de Meta
# ---------------------------------------------------------------------------


def _extract_meta_message(body: dict[str, Any]) -> dict[str, Any] | None:
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
        imagen_ref = (msg.get("image") or {}).get("id")
    elif msg_type == "interactive":
        interactive_data = msg.get("interactive") or {}
        button_reply = interactive_data.get("button_reply") or {}
        text = button_reply.get("id", "")
    elif msg_type == "audio":
        text = "[audio]"
    elif msg_type == "document":
        text = "[documento]"

    wa_id = msg.get("from", "")

    return {
        "canal": "whatsapp",
        "tipo": "imagen" if msg_type == "image" else "texto",
        "text": text.strip(),
        "imagen_ref": imagen_ref,
        "chat_id": wa_id,
        "sender": wa_id,
        "nombre": (contact.get("profile") or {}).get("name", ""),
    }


# ---------------------------------------------------------------------------
# Descargar imagen de Meta (Graph API)
# ---------------------------------------------------------------------------


def _download_meta_image(media_id: str, access_token: str, *, timeout: float = 30.0) -> bytes | None:
    try:
        with httpx.Client(timeout=timeout) as client:
            url_resp = client.get(
                f"https://graph.facebook.com/v19.0/{media_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            url_resp.raise_for_status()
            download_url = url_resp.json().get("url")
            if not download_url:
                return None
            img_resp = client.get(download_url, headers={"Authorization": f"Bearer {access_token}"})
            img_resp.raise_for_status()
            return img_resp.content
    except Exception:
        log.exception("Failed to download Meta image %s", media_id)
        return None


# ---------------------------------------------------------------------------
# Enviar mensaje por Meta
# ---------------------------------------------------------------------------


def _send_meta_message(chat_id: str, text: str, settings: Settings, buttons: list[tuple[str, str]] | None = None) -> None:
    if not settings.meta_access_token or not settings.meta_phone_number_id:
        print(f"[META] SKIP: no credentials for {chat_id}")
        return

    if buttons:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": chat_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": bid, "title": btitle}}
                        for bid, btitle in buttons[:3]
                    ]
                },
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": chat_id,
            "text": {"body": text},
        }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"https://graph.facebook.com/v19.0/{settings.meta_phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {settings.meta_access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            print(f"[META] ✅ sent to {chat_id}: {text[:60]}")
    except Exception as exc:
        print(f"[META] ❌ FAIL sending to {chat_id}: {text[:60]} — {exc}")


# ---------------------------------------------------------------------------
# Webhook principal
# ---------------------------------------------------------------------------


@router.api_route("/meta-webhook", methods=["GET", "POST"])
async def meta_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dep)],
    notifier: Annotated[Notifier, Depends(get_notifier_dep)],
    settings: Annotated[Settings, Depends(get_settings)],
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    # ── Verificación (GET) ──
    if request.method == "GET":
        if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
            return Response(content=str(hub_challenge or ""), media_type="text/plain")
        return Response(content="Verification failed", status_code=403)

    # ── Mensaje entrante (POST) ──
    body = await request.json()
    msg = _extract_meta_message(body)
    if msg is None:
        return Response(content="ok", media_type="text/plain")

    log.info("Meta webhook: chat=%s tipo=%s text=%s", msg["chat_id"], msg["tipo"], str(msg["text"])[:50])

    # Descargar y embeber imagen si es foto
    if msg["tipo"] == "imagen" and msg["imagen_ref"] and settings.meta_access_token:
        image_bytes = _download_meta_image(msg["imagen_ref"], settings.meta_access_token,
                                           timeout=settings.image_download_timeout_seconds)
        if image_bytes:
            msg["_image_bytes"] = image_bytes
            msg["_embedding"] = matcher.embed(image_bytes)
            save_embedding_for_chat(msg["chat_id"], msg["_embedding"])
        else:
            _send_meta_message(msg["chat_id"], "❌ No se pudo descargar la imagen. Intentá de nuevo.", settings)
            return Response(content="ok", media_type="text/plain")

    # Motor conversacional
    result = run_conversation_motor(msg)

    # Respuesta conversacional
    if result.get("accion") is None:
        text = result.get("respuesta", "Listo.")
        btns = result.get("buttons")
        _send_meta_message(msg["chat_id"], text, settings, buttons=btns)
        return Response(content="ok", media_type="text/plain")

    accion = result["accion"]
    chat_id = result["chat_id"]
    datos = result.get("datos", {})

    # ── REGISTRAR ──
    if accion == "registrar_persona":
        embedding = msg.get("_embedding") or result.get("_embedding")
        if embedding:
            report = _meta_register_with_embedding(session, settings, result, datos, chat_id, list(embedding))
        else:
            report = bot_intake.register_missing_person(
                session, matcher, settings, datos=datos,
                imagen_ref=result.get("imagen_ref"), chat_id=chat_id,
                channel=result.get("canal", "whatsapp"),
                sender=result.get("sender", ""), reporter_name=result.get("nombre"),
            )
        _send_meta_message(chat_id, f"✅ Registro creado (ID: {report.id}). Gracias por ayudar.", settings,
                           buttons=[("menu", "Menu")])
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
            # Guardar en estado para que el usuario pueda marcar como encontrado
            if match.missing_person_id:
                set_conversation_state(chat_id, {
                    "paso": "buscar_resultado",
                    "person_id": match.missing_person_id,
                    "person_name": match.full_name,
                    "person_status": match.status,
                })
            info = _format_person_info(match)
            _send_meta_message(chat_id, info, settings)
            _send_meta_message(chat_id, "¿Marcar como encontrada?", settings,
                               buttons=[("marcar", "Marcar encontrada"), ("menu", "Menu")])
        else:
            set_conversation_state(chat_id, None)
            _send_meta_message(chat_id, "❌ No se encontró match facial.", settings,
                               buttons=[("menu", "Menu")])
        return Response(content="ok", media_type="text/plain")

    # ── BUSCAR POR CÉDULA ──
    if accion == "buscar_por_cedula":
        cedula = datos.get("query", "")
        from app.services.search import find_missing_person_by_cedula
        person = find_missing_person_by_cedula(session, cedula) if cedula else None
        if person:
            linked = _get_linked_bot_report(session, person.id)
            set_conversation_state(chat_id, {
                "paso": "buscar_resultado",
                "person_id": person.id,
                "person_name": person.full_name,
                "person_status": person.status,
            })
            if linked:
                linked._linked_location = person.last_known_location
                linked._linked_cedula = person.cedula_masked
                info = _format_person_info(linked)
            else:
                info = _format_missing_person_info(person)
            _send_meta_message(chat_id, info, settings)
            if person.status != "found":
                _send_meta_message(chat_id, "¿Marcar como encontrada?", settings,
                                   buttons=[("marcar", "Marcar encontrada"), ("menu", "Menu")])
            else:
                _send_meta_message(chat_id, "¿Qué deseás hacer?", settings,
                                   buttons=[("menu", "Menu")])
        else:
            set_conversation_state(chat_id, None)
            _send_meta_message(chat_id, f"❌ No se encontró a nadie con cédula *{cedula}*.", settings,
                               buttons=[("menu", "Menu")])
        return Response(content="ok", media_type="text/plain")

    # ── BUSCAR POR NOMBRE ──
    if accion == "buscar_por_nombre":
        name = datos.get("query", "")
        person = bot_intake.search_by_name(session, name) if name else None
        if person:
            linked = _get_linked_bot_report(session, person.id)
            set_conversation_state(chat_id, {
                "paso": "buscar_resultado",
                "person_id": person.id,
                "person_name": person.full_name,
                "person_status": person.status,
            })
            if linked:
                linked._linked_location = person.last_known_location
                linked._linked_cedula = person.cedula_masked
                info = _format_person_info(linked)
            else:
                info = _format_missing_person_info(person)
            _send_meta_message(chat_id, info, settings)
            if person.status != "found":
                _send_meta_message(chat_id, "¿Marcar como encontrada?", settings,
                                   buttons=[("marcar", "Marcar encontrada"), ("menu", "Menu")])
            else:
                _send_meta_message(chat_id, "¿Qué deseás hacer?", settings,
                                   buttons=[("menu", "Menu")])
        else:
            set_conversation_state(chat_id, None)
            _send_meta_message(chat_id, f"❌ No se encontró a *{name}*.", settings,
                               buttons=[("menu", "Menu")])
        return Response(content="ok", media_type="text/plain")

    # ── MARCAR COMO ENCONTRADO ──
    if accion == "marcar_encontrado":
        person_id = datos.get("person_id")
        if person_id:
            from sqlmodel import select as _sel
            from app.models import MissingPerson, BotReport, utc_now
            now = utc_now()
            person = session.get(MissingPerson, person_id)
            if person and person.status != "found":
                person.status = "found"
                person.updated_at = now
                session.add(person)
                # Actualizar también todos los BotReports vinculados
                linked_reports = session.exec(
                    _sel(BotReport).where(BotReport.missing_person_id == person_id)
                ).all()
                for rp in linked_reports:
                    if rp.status != "found":
                        rp.status = "found"
                        rp.found_at = now
                        rp.updated_at = now
                        session.add(rp)
                session.commit()
                _send_meta_message(chat_id, f"✅ *{person.full_name}* marcada como *encontrada*. ¡Gracias por ayudar!", settings,
                                   buttons=[("menu", "Menu")])
            else:
                _send_meta_message(chat_id, "✅ Esa persona ya estaba marcada como encontrada.", settings,
                                   buttons=[("menu", "Menu")])
        else:
            _send_meta_message(chat_id, "No se pudo identificar a la persona.", settings,
                               buttons=[("menu", "Menu")])
        return Response(content="ok", media_type="text/plain")

    return Response(content="ok", media_type="text/plain")


# ---------------------------------------------------------------------------
# Helpers de registro y búsqueda
# ---------------------------------------------------------------------------


def _meta_register_with_embedding(
    session: Session, settings: Settings,
    result: dict[str, Any], datos: dict[str, Any],
    chat_id: str, embedding: list[float] | None,
) -> Any:
    import uuid
    from app.models import BotReport, MissingPerson, utc_now

    full_name = (datos.get("nombre") or "").strip() or "Desconocido"
    external_id = uuid.uuid4().hex
    person = MissingPerson(
        source=settings.bot_source, external_id=external_id,
        full_name=full_name, status="missing",
        cedula_masked=datos.get("cedula"),
        last_known_location=datos.get("ubicacion"),
        photo_url=result.get("imagen_ref"), source_date=utc_now(),
    )
    session.add(person)
    session.flush()

    report = BotReport(
        missing_person_id=person.id,
        channel=result.get("canal", "whatsapp"), chat_id=chat_id,
        sender=result.get("sender", ""), reporter_name=result.get("nombre"),
        contact=datos.get("contacto"), full_name=full_name,
        age=str(datos["edad"]) if datos.get("edad") is not None else None,
        description=datos.get("descripcion"),
        location=datos.get("ubicacion"),
        photo_url=result.get("imagen_ref"),
        face_embedding=embedding, status="missing",
        datos_raw=dict(datos),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _meta_search_by_embedding(
    session: Session, notifier: Notifier, settings: Settings,
    *, query_embedding: list[float],
    searcher_chat_id: str | None = None,
    searcher_contact: str | None = None,
) -> Any | None:
    from sqlmodel import select
    from app.models import BotReport, MissingPerson, utc_now

    candidates = session.exec(select(BotReport).where(BotReport.status == "missing")).all()

    best_report = None
    best_score = settings.face_match_threshold
    for candidate in candidates:
        if candidate.face_embedding is None:
            continue
        score = cosine_similarity(query_embedding, list(candidate.face_embedding))
        if score >= best_score:
            best_score = score
            best_report = candidate

    if best_report is None:
        return None

    from app.models import utc_now
    now = utc_now()

    # Cargar datos del MissingPerson vinculado para mostrar en la respuesta
    if best_report.missing_person_id is not None:
        person = session.get(MissingPerson, best_report.missing_person_id)
        if person is not None:
            best_report._linked_location = person.last_known_location
            best_report._linked_cedula = person.cedula_masked

    # Notificar al reportante (NO cambia status — eso lo hace el usuario)
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


def _format_person_info(report: Any) -> str:
    parts = [f"✅ *{report.full_name}*"]
    if getattr(report, "age", None):
        parts.append(f"👤 Edad: {report.age}")
    if getattr(report, "description", None):
        parts.append(f"📝 Descripción: {report.description}")
    ubicacion = getattr(report, "location", None)
    if not ubicacion and getattr(report, "_linked_location", None):
        ubicacion = report._linked_location
    if ubicacion:
        parts.append(f"📍 Última ubicación: {ubicacion}")
    if getattr(report, "contact", None):
        parts.append(f"📞 Contacto: {report.contact}")
    if getattr(report, "_linked_cedula", None) or getattr(report, "cedula_masked", None):
        parts.append(f"🪪 Cédula: {getattr(report, '_linked_cedula', None) or getattr(report, 'cedula_masked', None)}")
    status_text = "🟢 Encontrado/a" if report.status == "found" else "🔴 Desaparecido/a"
    parts.append(status_text)
    return "\n".join(parts)


def _format_missing_person_info(person: Any) -> str:
    """Formatea info de un MissingPerson (cuando no hay BotReport vinculado)."""
    parts = [f"✅ *{person.full_name}*"]
    if getattr(person, "cedula_masked", None):
        parts.append(f"🪪 Cédula: {person.cedula_masked}")
    if getattr(person, "last_known_location", None):
        parts.append(f"📍 Última ubicación: {person.last_known_location}")
    status_text = "🟢 Encontrado/a" if person.status == "found" else "🔴 Desaparecido/a"
    parts.append(status_text)
    return "\n".join(parts)


def _get_linked_bot_report(session: Session, missing_person_id: int) -> Any | None:
    from sqlmodel import select
    from app.models import BotReport
    return session.exec(
        select(BotReport).where(BotReport.missing_person_id == missing_person_id)
    ).first()
