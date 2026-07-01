"""Motor conversacional compartido entre todos los canales.

Contiene: estado, helpers, motor principal.
Los handlers estan en ``conversation_handlers.py``.
"""

from typing import Any

from app.messaging.session_store import (
    ConversationStateStore,
    get_default_conversation_state_store,
)

GREETINGS = {
    "hola", "buenas", "buenos dias", "buenos días",
    "buenas tardes", "buenas noches", "hello", "hi",
}
MENU_COMMAND = "menu"
HELP_COMMANDS = {"3", "ayuda"}
PRIMARY_SOURCE_URL = "https://venezuelatebusca.com/"
SEARCH_PERSON_TITLE = "Buscar persona"
REGISTER_PERSON_TITLE = "Registrar persona"
HELP_TITLE = "Ayuda"
MAIN_MENU_BUTTON_TITLE = "Menu principal"
MAIN_MENU_BUTTON = ("menu", MAIN_MENU_BUTTON_TITLE)
REGISTER_COMMANDS = {"2", "registrar", "registrar persona"}
SEARCH_PERSON_COMMANDS = {"1", "buscar", "buscar persona"}
SEARCH_QUERY_COMMANDS = {
    "1",
    "buscar por cedula o nombre",
    "buscar por cédula o nombre",
}
SEARCH_PHOTO_COMMANDS = {"2", "buscar por foto"}
MARK_FOUND_COMMANDS = {"marcar", "marcar encontrada"}
CONFIRM_COMMANDS = {"si", "confirmar"}


def _store(store: ConversationStateStore | None = None) -> ConversationStateStore:
    return store or get_default_conversation_state_store()


def get_conversation_state(chat_id: str, store: ConversationStateStore | None = None) -> dict[str, Any]:
    return _store(store).get_state(chat_id)


def set_conversation_state(
    chat_id: str,
    data: dict[str, Any] | None,
    store: ConversationStateStore | None = None,
) -> None:
    _store(store).set_state(chat_id, data)


def save_embedding_for_chat(
    chat_id: str,
    embedding: list[float] | None,
    store: ConversationStateStore | None = None,
) -> None:
    _store(store).save_embedding(chat_id, embedding)


def make_response(
    chat_id: str,
    canal: str,
    text: str,
    accion: str | None = None,
    buttons: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"chat_id": chat_id, "canal": canal, "respuesta": text, "accion": accion}
    if buttons:
        out["buttons"] = buttons
    return out


def menu_response(chat_id: str, canal: str) -> dict[str, Any]:
    return make_response(
        chat_id,
        canal,
        (
            "🤖 *BuscaChat* - Asistente de busqueda humanitaria\n\n"
            "Enviame un nombre o numero de cédula para buscar personas localizadas, "
            "desaparecidas o fuentes de informacion disponibles.\n\n"
            "Elige una de las opciones:"
        ),
        buttons=[("1", SEARCH_PERSON_TITLE), ("2", REGISTER_PERSON_TITLE), ("3", HELP_TITLE)],
    )


def search_mode_response(chat_id: str, canal: str) -> dict[str, Any]:
    return make_response(
        chat_id, canal,
        "🔎 *Busqueda de persona*\n\n"
        "Puedes buscar usando el *numero de cédula o nombre*, "
        "o usando una *foto del rostro*.\n\n"
        "Elige una de las opciones:",
        buttons=[("1", "Buscar por cédula o nombre"), ("2", "Buscar por foto")],
    )


def run_conversation_motor(msg: dict[str, Any], store: ConversationStateStore | None = None) -> dict[str, Any]:
    chat_id = msg["chat_id"]
    text = msg.get("text", "").strip().casefold()

    if text == MENU_COMMAND:
        set_conversation_state(chat_id, {"paso": "menu"}, store)
        return menu_response(chat_id, msg["canal"])

    state = get_conversation_state(chat_id, store)
    paso = state.get("paso", "menu")

    # -- Lazy import para evitar circular imports --
    from app.messaging.conversation_handlers import (
        handle_buscar_cedula,
        handle_buscar_foto,
        handle_buscar_modo,
        handle_buscar_modo_foto,
        handle_buscar_nombre,
        handle_buscar_ocr,
        handle_buscar_query,
        handle_buscar_resultado,
        handle_menu,
        handle_reg_cedula,
        handle_reg_cedula_ocr,
        handle_reg_confirmar,
        handle_reg_contacto,
        handle_reg_descripcion,
        handle_reg_edad,
        handle_reg_foto,
        handle_reg_nombre,
        handle_reg_ocr_confirmar,
        handle_reg_ubicacion,
    )

    if paso == "menu":
        return handle_menu(msg, chat_id, text, store)
    if paso == "buscar_modo":
        return handle_buscar_modo(msg, chat_id, text, store)
    if paso == "buscar_modo_foto":
        return handle_buscar_modo_foto(msg, chat_id, text, store)
    if paso == "buscar_query":
        return handle_buscar_query(msg, chat_id, text, store)
    if paso == "buscar_foto":
        return handle_buscar_foto(msg, chat_id, store)
    if paso == "buscar_ocr":
        return handle_buscar_ocr(msg, chat_id, store)
    if paso == "buscar_nombre":
        return handle_buscar_nombre(msg, chat_id, text, store)
    if paso == "buscar_cedula":
        return handle_buscar_cedula(msg, chat_id, text, store)
    if paso == "buscar_resultado":
        return handle_buscar_resultado(msg, chat_id, text, store)
    if paso == "reg_nombre":
        return handle_reg_nombre(msg, chat_id, text, store)
    if paso == "reg_cedula_ocr":
        return handle_reg_cedula_ocr(msg, chat_id, store)
    if paso == "reg_ocr_confirmar":
        return handle_reg_ocr_confirmar(msg, chat_id, text, store)
    if paso == "reg_edad":
        return handle_reg_edad(msg, chat_id, text, store)
    if paso == "reg_cedula":
        return handle_reg_cedula(msg, chat_id, text, store)
    if paso == "reg_ubicacion":
        return handle_reg_ubicacion(msg, chat_id, text, store)
    if paso == "reg_descripcion":
        return handle_reg_descripcion(msg, chat_id, text, store)
    if paso == "reg_foto":
        return handle_reg_foto(msg, chat_id, store)
    if paso == "reg_contacto":
        return handle_reg_contacto(msg, chat_id, text, store)
    if paso == "reg_confirmar":
        return handle_reg_confirmar(msg, chat_id, text, store)

    return menu_response(chat_id, msg["canal"])
