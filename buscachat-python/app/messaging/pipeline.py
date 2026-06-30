import logging
from typing import Any
from urllib.parse import quote_plus

import httpx
from opentelemetry import trace
from sqlmodel import Session, select

from app.adapters.green_api import Notifier
from app.adapters.venezuela_te_busca import VenezuelaTeBuscaSearchResult, search_venezuela_te_busca
from app.config import Settings
from app.face import FaceMatcher
from app.messaging.conversation import run_conversation_motor, set_conversation_state
from app.messaging.session_store import ConversationStateStore
from app.messaging.types import Button, GenericInboundMessage, GenericOutboundMessage
from app.models import BotReport, MissingPerson
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
        try:
            result = (
                search_venezuela_te_busca(
                    query,
                    base_url=settings.venezuela_te_busca_base_url,
                    timeout=settings.venezuela_te_busca_timeout_seconds,
                    limit=10,
                )
                if query
                else VenezuelaTeBuscaSearchResult(query="")
            )
        except (httpx.HTTPError, ValueError) as exc:
            log.exception(
                "Venezuela Te Busca search failed in message pipeline",
                extra={"chat_id": chat_id, "action": action, "query": query},
            )
            trace.get_current_span().record_exception(exc)
            set_conversation_state(chat_id, None, conversation_store)
            return GenericOutboundMessage(
                source=message.source,
                chat_id=chat_id,
                text=(
                    "No puedo consultar en este momento. "
                    "Intenta de nuevo en unos minutos o prueba con otra busqueda."
                ),
                action=action,
                buttons=_search_navigation_buttons(),
            )
        except Exception as exc:
            log.exception(
                "Unexpected search failure in message pipeline",
                extra={"chat_id": chat_id, "action": action, "query": query},
            )
            trace.get_current_span().record_exception(exc)
            set_conversation_state(chat_id, None, conversation_store)
            return GenericOutboundMessage(
                source=message.source,
                chat_id=chat_id,
                text=(
                    "No puedo consultar en este momento. "
                    "Intenta de nuevo en unos minutos o prueba con otra busqueda."
                ),
                action=action,
                buttons=_search_navigation_buttons(),
            )
        return _external_search_response(message, chat_id, action, query, result, conversation_store)

    if action == "buscar_por_ocr":
        nombre = datos.get("nombre_ocr")
        cedula = datos.get("cedula_ocr")
        from app.services.search import find_missing_person_by_cedula
        person = find_missing_person_by_cedula(session, cedula) if cedula else None
        if not person and nombre:
            people = bot_intake.search_by_name_matches(session, nombre, limit=10)
            if people:
                return _format_name_search_results(message, session, chat_id, action, nombre, people, conversation_store)
        if person:
            return _format_name_search_results(message, session, chat_id, action, nombre or cedula or "", [person], conversation_store)
        set_conversation_state(chat_id, None, conversation_store)
        return GenericOutboundMessage(
            source=message.source, chat_id=chat_id,
            text="No se pudo extraer informacion de la cedula. Intenta buscar manualmente.",
            action=action, buttons=[Button(id="menu", title="Menu principal")],
        )

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
            buttons=_search_navigation_buttons(),
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

    buttons = _search_navigation_buttons()
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


def _search_people_response(
    message: GenericInboundMessage,
    session: Session,
    chat_id: str,
    action: str,
    query: str,
    people: list[MissingPerson],
    conversation_store: ConversationStateStore | None,
) -> GenericOutboundMessage:
    if not people:
        set_conversation_state(chat_id, None, conversation_store)
        return GenericOutboundMessage(
            source=message.source,
            chat_id=chat_id,
            text=(
                f"❌ No encontramos resultados para *{query}*.\n\n"
                "Puedes intentar con otro nombre, un apellido, cédula o una foto clara del rostro."
            ),
            action=action,
            buttons=_search_navigation_buttons(),
        )

    linked_reports = _get_linked_bot_reports_by_person_id(session, [person.id for person in people])
    text = _format_name_search_results(query, people, linked_reports)
    buttons = _search_navigation_buttons()

    if len(people) == 1:
        person = people[0]
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
        if person.status != "found":
            text += "\n\nResponde *marcar* para marcarla como encontrada."
            buttons.insert(0, Button(id="marcar", title="Marcar encontrada"))
    else:
        set_conversation_state(chat_id, None, conversation_store)

    return GenericOutboundMessage(
        source=message.source,
        chat_id=chat_id,
        text=text,
        action=action,
        buttons=buttons,
    )


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
        {},
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


def _get_linked_bot_report(session: Any, missing_person_id: int | None) -> BotReport | None:
    if session is None or missing_person_id is None:
        return None
    return session.exec(select(BotReport).where(BotReport.missing_person_id == missing_person_id)).first()


def _get_linked_bot_reports_by_person_id(
    session: Any,
    missing_person_ids: list[int | None],
) -> dict[int, BotReport]:
    person_ids = [person_id for person_id in missing_person_ids if person_id is not None]
    if session is None or not person_ids:
        return {}

    reports = session.exec(select(BotReport).where(BotReport.missing_person_id.in_(person_ids))).all()
    linked: dict[int, BotReport] = {}
    for report in reports:
        if report.missing_person_id is not None and report.missing_person_id not in linked:
            linked[report.missing_person_id] = report
    return linked


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


def _format_missing_person(person: Any) -> str:
    parts = [f"*{person.full_name}*"]
    if getattr(person, "cedula_masked", None):
        parts.append(f"🪪 Cédula: {person.cedula_masked}")
    location = _person_location(person)
    if location:
        parts.append(f"📍 Direccion/ubicacion: {location}")
    parts.append(f"*Orígen:* {_source_search_url(person.full_name)}")
    parts.append(_format_status(person.status))
    return "\n".join(parts)


def _format_name_search_results(
    query: str,
    people: list[Any],
    linked_reports: dict[int, BotReport],
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
        report = linked_reports.get(person.id) if person.id is not None else None
        blocks.append(_format_name_search_result(index, person, report))
    return "\n\n".join(blocks)


def _format_name_search_result(index: int, person: Any, report: BotReport | None) -> str:
    name = report.full_name if report else person.full_name
    location = _report_location(report, person) if report else _person_location(person)
    lines = [
        f"{index}. *Estado:* {_format_status_text(person.status)}",
        f"*Nombre:* {name}",
        f"*Ubicación:* {location or 'no disponible'}",
        f"*Orígen:* {_source_person_url(person, person.full_name)}",
    ]
    age = report.age if report else getattr(person, "age", None)
    if age:
        lines.insert(2, f"*Edad:* {age}")
    if person.cedula_masked:
        lines.append(f"*Cédula:* {person.cedula_masked}")
    lines.extend(_status_detail_lines(person))
    return "\n".join(lines)


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


def _report_location(report: BotReport | None, person: MissingPerson) -> str | None:
    if report and report.location:
        return report.location
    return _person_location(person)


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
