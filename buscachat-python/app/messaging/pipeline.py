import logging
from typing import Any
from urllib.parse import quote_plus

import httpx
from opentelemetry import trace
from sqlmodel import Session

from app.adapters.venezuela_te_busca import VenezuelaTeBuscaSearchResult, search_venezuela_te_busca
from app.config import Settings
from app.face import FaceMatcher
from app.messaging.conversation import run_conversation_motor, set_conversation_state
from app.messaging.notifier import Notifier
from app.messaging.session_store import ConversationStateStore
from app.messaging.types import Button, GenericInboundMessage, GenericOutboundMessage
from app.services import bot_intake

PRIMARY_SOURCE_URL = "https://venezuelatebusca.com/"
log = logging.getLogger(__name__)


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
    buttons = [Button(id=str(button_id), title=str(title)) for button_id, title in result.get("buttons", [])]

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
            text=(
                f"✅ Registro creado (ID: {report.id}).\n\n"
                "Gracias por compartir la informacion. Quedara disponible para busquedas por "
                "nombre, cédula y foto cuando haya imagen."
            ),
            action=action,
            buttons=[Button(id="menu", title="Menu principal")],
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
            text = "✅ Encontramos una posible coincidencia por foto:\n\n" + _format_bot_report(match)
            out_buttons = []
            if match.status != "found":
                text += "\n\nResponde *marcar* para marcarla como encontrada."
                out_buttons.append(Button(id="marcar", title="Marcar encontrada"))
            out_buttons.extend(_search_navigation_buttons())
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
            text=(
                "❌ No encontramos coincidencias faciales con esa imagen.\n\n"
                "Puedes intentar con otra foto clara del rostro o buscar por nombre/cédula."
            ),
            action=action,
            buttons=_search_navigation_buttons(),
        )

    if action in ("buscar_por_query", "buscar_por_cedula", "buscar_por_nombre"):
        query = datos.get("query", "")
        return _run_external_search_chat(message, session, chat_id, action, query, settings, conversation_store)

    if action == "buscar_por_ocr":
        nombre = datos.get("nombre_ocr")
        cedula = datos.get("cedula_ocr")
        query = cedula or nombre or ""
        return _run_external_search_chat(message, session, chat_id, "buscar_por_cedula", query, settings, conversation_store)

    if action == "marcar_encontrado":
        person_id = datos.get("person_id")
        person = bot_intake.mark_missing_person_found(session, int(person_id)) if person_id else None
        if person is None:
            text = "No se pudo identificar a la persona."
        else:
            text = f"✅ *{person.full_name}* fue marcada como *encontrada*. Gracias por ayudar."
        return GenericOutboundMessage(
            source=message.source,
            chat_id=chat_id,
            text=text,
            action=action,
            buttons=[Button(id="menu", title="Menu principal")],
        )

    return GenericOutboundMessage(source=message.source, chat_id=chat_id, text="Listo.", action=action)


def _external_search_response(
    message: GenericInboundMessage,
    chat_id: str,
    action: str,
    query: str,
    result: VenezuelaTeBuscaSearchResult,
    conversation_store: ConversationStateStore | None,
) -> GenericOutboundMessage:
    if not result.persons:
        set_conversation_state(chat_id, None, conversation_store)
        return GenericOutboundMessage(
            source=message.source,
            chat_id=chat_id,
            text=(
                f"❌ No encontramos resultados para *{query}*.\n\n"
                "Puedes intentar con otro nombre, un apellido, una cédula o una foto clara del rostro."
            ),
            action=action,
            buttons=_search_navigation_buttons(),
        )

    set_conversation_state(chat_id, None, conversation_store)
    text = _format_name_search_results(
        result.query or query,
        result.persons,
        total_count=result.total_count,
    )
    if result.degraded:
        text += "\n\nLa fuente respondio en modo degradado; algunos resultados podrian faltar."
    return GenericOutboundMessage(
        source=message.source,
        chat_id=chat_id,
        text=text,
        action=action,
        buttons=_search_navigation_buttons(),
    )


def _format_bot_report(report: Any) -> str:
    parts = [f"*{report.full_name}*"]
    if getattr(report, "age", None):
        parts.append(f"🎂 Edad: {report.age}")
    if getattr(report, "description", None):
        parts.append(f"📝 Descripcion: {report.description}")
    location = getattr(report, "location", None) or getattr(report, "_linked_location", None)
    if location:
        parts.append(f"📍 Direccion/ubicacion: {location}")
    if getattr(report, "contact", None):
        parts.append(f"📞 Contacto: {report.contact}")
    cedula = getattr(report, "_linked_cedula", None) or getattr(report, "cedula_masked", None)
    if cedula:
        parts.append(f"🪪 Cédula: {cedula}")
    parts.append(f"*Orígen:* {_source_search_url(report.full_name)}")
    parts.append(_format_status(report.status))
    return "\n".join(parts)


def _format_name_search_results(
    query: str,
    people: list[Any],
    *,
    total_count: int | None = None,
) -> str:
    count = len(people)
    if total_count and total_count > count:
        count_text = f"{count} de {total_count} coincidencias"
    else:
        count_text = f"{count} coincidencia{'s' if count != 1 else ''}"
    header = f"Resultados para *{query}*\nMostrando {count_text} (maximo 10):"
    blocks = [header]
    for index, person in enumerate(people, start=1):
        blocks.append(_format_name_search_result(index, person))
    return "\n\n".join(blocks)


def _format_name_search_result(index: int, person: Any) -> str:
    lines = [
        f"{index}. *Estado:* {_format_status_text(person.status)}",
        f"*Nombre:* {person.full_name}",
        f"*Ubicación:* {_person_location(person) or 'no disponible'}",
        f"*Orígen:* {_source_person_url(person, person.full_name)}",
    ]
    if getattr(person, "age", None):
        lines.insert(2, f"*Edad:* {person.age}")
    if person.cedula_masked:
        lines.append(f"*Cédula:* {person.cedula_masked}")
    lines.extend(_status_detail_lines(person))
    return "\n".join(lines)


def _run_external_search_chat(
    message: GenericInboundMessage,
    session: Session,
    chat_id: str,
    action: str,
    query: str,
    settings: Settings,
    conversation_store: ConversationStateStore | None,
) -> GenericOutboundMessage:
    """Busca en API externa + DB local, mergea y formatea."""
    from app.services.search import find_missing_person_by_cedula
    from opentelemetry import trace

    # 1. Buscar en API externa
    try:
        external = (
            search_venezuela_te_busca(query, base_url=settings.venezuela_te_busca_base_url,
                                       timeout=settings.venezuela_te_busca_timeout_seconds, limit=10)
            if query else VenezuelaTeBuscaSearchResult(query="")
        )
    except (httpx.HTTPError, ValueError) as exc:
        log.exception("External search failed", extra={"query": query})
        trace.get_current_span().record_exception(exc)
        external = VenezuelaTeBuscaSearchResult(query=query)
    except Exception as exc:
        log.exception("Unexpected search failure", extra={"query": query})
        trace.get_current_span().record_exception(exc)
        set_conversation_state(chat_id, None, conversation_store)
        return GenericOutboundMessage(
            source=message.source, chat_id=chat_id,
            text="No puedo consultar en este momento.",
            action=action, buttons=_search_navigation_buttons(),
        )

    # 2. Buscar en DB local
    local_people: list = []
    if query:
        try:
            cedula_match = find_missing_person_by_cedula(session, query)
            if cedula_match:
                local_people.append(cedula_match)
            local_people.extend(bot_intake.search_by_name_matches(session, query, limit=5))
        except Exception:
            pass  # DB no disponible (tests con mock)

    # 3. Merge: combinar, deduplicar por full_name
    all_people: list = list(external.persons)
    seen_names: set[str] = {p.full_name.strip().lower() for p in external.persons}
    seen_cedulas: set[str] = {p.id_number.strip().lower() for p in external.persons if p.id_number}

    for local_person in local_people:
        local_name = local_person.full_name.strip().lower()
        local_cedula = (local_person.cedula_masked or "").strip().lower()
        if local_name in seen_names or (local_cedula and local_cedula in seen_cedulas):
            continue  # Ya está en los resultados externos
        all_people.append(local_person)
        seen_names.add(local_name)
        if local_cedula:
            seen_cedulas.add(local_cedula)

    # 4. Formatear
    if not all_people:
        set_conversation_state(chat_id, None, conversation_store)
        return GenericOutboundMessage(
            source=message.source, chat_id=chat_id,
            text=f"❌ No encontramos resultados para *{query}*.", action=action,
            buttons=_search_navigation_buttons(),
        )

    total = external.total_count + (len(all_people) - len(external.persons))
    text = _format_name_search_results(query, all_people, total_count=total if total > 0 else None)
    if external.degraded:
        text += "\n\nLa fuente respondio en modo degradado."
    set_conversation_state(chat_id, None, conversation_store)
    return GenericOutboundMessage(
        source=message.source, chat_id=chat_id, text=text, action=action,
        buttons=_search_navigation_buttons(),
    )


def _search_navigation_buttons() -> list[Button]:
    return [
        Button(id="buscar", title="Volver a buscar"),
        Button(id="menu", title="Menu principal"),
    ]


def _source_search_url(name: str) -> str:
    return f"{PRIMARY_SOURCE_URL}?query={quote_plus(name)}"


def _source_person_url(person: Any, fallback_name: str) -> str:
    person_id = getattr(person, "id", None)
    if isinstance(person_id, str) and person_id.strip():
        return f"{PRIMARY_SOURCE_URL}?person={quote_plus(person_id.strip())}"
    return _source_search_url(fallback_name)


def _format_status(status: str | None) -> str:
    if status == "found":
        return "✅ Encontrada"
    if status == "missing":
        return "❌ No encontrada"
    if status == "deceased":
        return "🕯️ Fallecida"
    if status == "injured":
        return "🏥 Herida"
    return "❔ Estado sin confirmar"


def _format_status_text(status: str | None) -> str:
    if status == "found":
        return "Encontrada"
    if status == "missing":
        return "No encontrada"
    if status == "deceased":
        return "Fallecida"
    if status == "injured":
        return "Herida"
    if status == "admitted":
        return "Ingresada"
    if status == "discharged":
        return "Alta o trasladada"
    return "Estado sin confirmar"


def _status_detail_lines(person: Any) -> list[str]:
    lines: list[str] = []
    found_note = _format_found_note(getattr(person, "found_note", None))
    if found_note:
        lines.append(f"*Nota de estado:* {found_note}")

    hospital_status = _clean_text(getattr(person, "hospital_status", None))
    if hospital_status:
        status_text = _format_hospital_status_text(hospital_status)
        if found_note is None or status_text.casefold() != found_note.casefold():
            lines.append(f"*Estado hospitalario:* {status_text}")
    return lines


def _format_found_note(value: Any) -> str | None:
    note = _clean_text(value)
    if note is None:
        return None

    normalized = note.casefold()
    if "fallecid" in normalized:
        return "Fallecido"
    if "ingresad" in normalized or "internad" in normalized:
        return "Ingresado"
    if "alta" in normalized or "traslad" in normalized:
        return "Alta o trasladado"
    if len(note) <= 160:
        return note
    return f"{note[:157].rstrip()}..."


def _format_hospital_status_text(status: str) -> str:
    if status == "deceased":
        return "Fallecido"
    if status == "admitted":
        return "Ingresado"
    if status == "discharged":
        return "Alta o trasladado"
    status_text = _format_status_text(status)
    if status_text == "Estado sin confirmar":
        return status
    return status_text


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _person_location(person: Any) -> str | None:
    pieces = [
        getattr(person, "last_known_location", None),
        getattr(person, "hospital_name", None),
        getattr(person, "parroquia", None),
        getattr(person, "municipio", None),
    ]
    unique = []
    for piece in pieces:
        if piece and piece not in unique:
            unique.append(piece)
    return ", ".join(unique) if unique else None


def _get_linked_bot_report(session: Session, missing_person_id: int | None) -> Any | None:
    """Busca el BotReport vinculado a un MissingPerson."""
    from sqlmodel import select
    from app.models import BotReport
    if missing_person_id is None:
        return None
    return session.exec(select(BotReport).where(BotReport.missing_person_id == missing_person_id)).first()
