from typing import Any

from sqlmodel import Session, select

from app.adapters.green_api import Notifier
from app.config import Settings
from app.face import FaceMatcher
from app.messaging.conversation import run_conversation_motor, set_conversation_state
from app.messaging.session_store import ConversationStateStore
from app.messaging.types import Button, GenericInboundMessage, GenericOutboundMessage
from app.models import BotReport, MissingPerson
from app.services import bot_intake
from app.services.search import find_missing_person_by_cedula


def run_message_pipeline(
    message: GenericInboundMessage,
    *,
    session: Session,
    matcher: FaceMatcher,
    notifier: Notifier,
    settings: Settings,
    conversation_store: ConversationStateStore | None = None,
) -> GenericOutboundMessage:
    result = run_conversation_motor(
        message.to_conversation_payload(),
        store=conversation_store,
    )
    buttons = [
        Button(id=str(button_id), title=str(title))
        for button_id, title in result.get("buttons", [])
    ]

    if result.get("accion") is None:
        return GenericOutboundMessage(
            source=message.source,
            chat_id=result["chat_id"],
            text=result.get("respuesta", "Listo."),
            buttons=buttons,
        )

    action = result["accion"]
    chat_id = result["chat_id"]
    datos = result.get("datos", {})

    if action == "registrar_persona":
        report = bot_intake.register_missing_person(
            session,
            matcher,
            settings,
            datos=datos,
            imagen_ref=result.get("imagen_ref"),
            chat_id=chat_id,
            channel=message.source.value,
            sender=result.get("sender", ""),
            reporter_name=result.get("nombre"),
            face_embedding=result.get("_embedding") or message.image_embedding,
        )
        return GenericOutboundMessage(
            source=message.source,
            chat_id=chat_id,
            text=f"Registro creado (ID: {report.id}). Gracias por ayudar.",
            action=action,
            buttons=[Button(id="menu", title="Menu")],
        )

    if action == "buscar_por_foto":
        match = bot_intake.search_by_photo(
            session,
            matcher,
            notifier,
            settings,
            datos=datos,
            imagen_ref=result.get("imagen_ref"),
            searcher_chat_id=chat_id,
            searcher_contact=datos.get("contacto") or result.get("sender", ""),
            query_embedding=result.get("_embedding") or message.image_embedding,
        )
        if match:
            if match.missing_person_id:
                set_conversation_state(
                    chat_id,
                    {
                        "paso": "buscar_resultado",
                        "person_id": match.missing_person_id,
                        "person_name": match.full_name,
                        "person_status": match.status,
                    },
                    conversation_store,
                )
            text = _format_bot_report(match)
            out_buttons = []
            if match.status != "found":
                text += "\n\nResponde *marcar* para marcarla como encontrada."
                out_buttons.append(Button(id="marcar", title="Marcar encontrada"))
            out_buttons.append(Button(id="menu", title="Menu"))
            return GenericOutboundMessage(
                source=message.source,
                chat_id=chat_id,
                text=text,
                action=action,
                buttons=out_buttons,
            )

        set_conversation_state(chat_id, None, conversation_store)
        return GenericOutboundMessage(
            source=message.source,
            chat_id=chat_id,
            text="No se encontro match facial.",
            action=action,
            buttons=[Button(id="menu", title="Menu")],
        )

    if action == "buscar_por_cedula":
        cedula = datos.get("query", "")
        person = find_missing_person_by_cedula(session, cedula) if cedula else None
        return _search_person_response(
            message,
            session,
            chat_id,
            action,
            person,
            f"No se encontro a nadie con cedula *{cedula}*.",
            conversation_store,
        )

    if action == "buscar_por_nombre":
        name = datos.get("query", "")
        person = bot_intake.search_by_name(session, name) if name else None
        return _search_person_response(
            message,
            session,
            chat_id,
            action,
            person,
            f"No se encontro a *{name}*.",
            conversation_store,
        )

    if action == "buscar_por_ocr":
        nombre = datos.get("nombre_ocr")
        cedula = datos.get("cedula_ocr")
        # Buscar primero por cédula, si no por nombre
        person = None
        if cedula:
            person = find_missing_person_by_cedula(session, cedula)
        if not person and nombre:
            person = bot_intake.search_by_name(session, nombre)
        return _search_person_response(
            message, session, chat_id, action, person,
            f"No se encontro a la persona de la cedula.",
            conversation_store,
        )

    if action == "marcar_encontrado":
        person_id = datos.get("person_id")
        person = bot_intake.mark_missing_person_found(session, int(person_id)) if person_id else None
        if person is None:
            text = "No se pudo identificar a la persona."
        else:
            text = f"*{person.full_name}* marcada como *encontrada*. Gracias por ayudar."
        return GenericOutboundMessage(
            source=message.source,
            chat_id=chat_id,
            text=text,
            action=action,
            buttons=[Button(id="menu", title="Menu")],
        )

    return GenericOutboundMessage(source=message.source, chat_id=chat_id, text="Listo.", action=action)


def _search_person_response(
    message: GenericInboundMessage,
    session: Session,
    chat_id: str,
    action: str,
    person: MissingPerson | None,
    not_found_text: str,
    conversation_store: ConversationStateStore | None,
) -> GenericOutboundMessage:
    if person is None:
        set_conversation_state(chat_id, None, conversation_store)
        return GenericOutboundMessage(
            source=message.source,
            chat_id=chat_id,
            text=not_found_text,
            action=action,
            buttons=[Button(id="menu", title="Menu")],
        )

    linked = _get_linked_bot_report(session, person.id)
    set_conversation_state(
        chat_id,
        {
            "paso": "buscar_resultado",
            "person_id": person.id,
            "person_name": person.full_name,
            "person_status": person.status,
        },
        conversation_store,
    )
    if linked:
        linked._linked_location = person.last_known_location
        linked._linked_cedula = person.cedula_masked
        text = _format_bot_report(linked)
    else:
        text = _format_missing_person(person)

    buttons = [Button(id="menu", title="Menu")]
    if person.status != "found":
        text += "\n\nResponde *marcar* para marcarla como encontrada."
        buttons.insert(0, Button(id="marcar", title="Marcar encontrada"))

    return GenericOutboundMessage(
        source=message.source,
        chat_id=chat_id,
        text=text,
        action=action,
        buttons=buttons,
    )


def _get_linked_bot_report(session: Any, missing_person_id: int | None) -> BotReport | None:
    if session is None or missing_person_id is None:
        return None
    return session.exec(
        select(BotReport).where(BotReport.missing_person_id == missing_person_id)
    ).first()


def _format_bot_report(report: Any) -> str:
    parts = [f"*{report.full_name}*"]
    if getattr(report, "age", None):
        parts.append(f"Edad: {report.age}")
    if getattr(report, "description", None):
        parts.append(f"Descripcion: {report.description}")
    location = getattr(report, "location", None) or getattr(report, "_linked_location", None)
    if location:
        parts.append(f"Ultima ubicacion: {location}")
    if getattr(report, "contact", None):
        parts.append(f"Contacto: {report.contact}")
    cedula = getattr(report, "_linked_cedula", None) or getattr(report, "cedula_masked", None)
    if cedula:
        parts.append(f"Cedula: {cedula}")
    parts.append("Encontrado/a" if report.status == "found" else "Desaparecido/a")
    return "\n".join(parts)


def _format_missing_person(person: Any) -> str:
    parts = [f"*{person.full_name}*"]
    if getattr(person, "cedula_masked", None):
        parts.append(f"Cedula: {person.cedula_masked}")
    if getattr(person, "last_known_location", None):
        parts.append(f"Ultima ubicacion: {person.last_known_location}")
    parts.append("Encontrado/a" if person.status == "found" else "Desaparecido/a")
    return "\n".join(parts)
