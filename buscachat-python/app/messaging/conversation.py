from typing import Any

from app.messaging.session_store import (
    ConversationStateStore,
    get_default_conversation_state_store,
)

GREETINGS = {
    "hola",
    "buenas",
    "buenos dias",
    "buenos días",
    "buenas tardes",
    "buenas noches",
    "hello",
    "hi",
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


def get_conversation_state(
    chat_id: str,
    store: ConversationStateStore | None = None,
) -> dict[str, Any]:
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
    out: dict[str, Any] = {
        "chat_id": chat_id,
        "canal": canal,
        "respuesta": text,
        "accion": accion,
    }
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
        chat_id,
        canal,
        (
            "🔎 *Busqueda de persona*\n\n"
            "Puedes buscar usando el *numero de cédula o nombre*, "
            "o usando una *foto del rostro*.\n\n"
            "Elige una de las opciones:"
        ),
        buttons=[
            ("1", "Buscar por cédula o nombre"),
            ("2", "Buscar por foto"),
        ],
    )


def run_conversation_motor(
    msg: dict[str, Any],
    store: ConversationStateStore | None = None,
) -> dict[str, Any]:
    chat_id = msg["chat_id"]
    text = msg.get("text", "").strip().casefold()

    if text == MENU_COMMAND:
        set_conversation_state(chat_id, {"paso": "menu"}, store)
        return menu_response(chat_id, msg["canal"])

    state = get_conversation_state(chat_id, store)
    paso = state.get("paso", "menu")

    if paso == "menu":
        return _handle_menu(msg, chat_id, text, store)
    if paso == "buscar_modo":
        return _handle_buscar_modo(msg, chat_id, text, store)
    if paso == "buscar_query":
        return _handle_buscar_query(msg, chat_id, text, store)
    if paso == "buscar_foto":
        return _handle_buscar_foto(msg, chat_id, store)
    if paso == "buscar_nombre":
        return _handle_buscar_nombre(msg, chat_id, text, store)
    if paso == "buscar_cedula":
        return _handle_buscar_cedula(msg, chat_id, text, store)
    if paso == "buscar_resultado":
        return _handle_buscar_resultado(msg, chat_id, text, store)
    if paso == "reg_nombre":
        return _handle_reg_nombre(msg, chat_id, text, store)
    if paso == "reg_edad":
        return _handle_reg_edad(msg, chat_id, text, store)
    if paso == "reg_cedula":
        return _handle_reg_cedula(msg, chat_id, text, store)
    if paso == "reg_ubicacion":
        return _handle_reg_ubicacion(msg, chat_id, text, store)
    if paso == "reg_descripcion":
        return _handle_reg_descripcion(msg, chat_id, text, store)
    if paso == "reg_foto":
        return _handle_reg_foto(msg, chat_id, store)
    if paso == "reg_contacto":
        return _handle_reg_contacto(msg, chat_id, text, store)
    if paso == "reg_confirmar":
        return _handle_reg_confirmar(msg, chat_id, text, store)

    return menu_response(chat_id, msg["canal"])


def _handle_menu(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    if text in SEARCH_PERSON_COMMANDS:
        set_conversation_state(chat_id, {"paso": "buscar_modo"}, store)
        return search_mode_response(chat_id, canal)
    if text in REGISTER_COMMANDS:
        set_conversation_state(chat_id, {"paso": "menu"}, store)
        return make_response(
            chat_id,
            canal,
            (
                "📝 *Registrar persona*\n\n"
                "Si quieres reportar a alguien, puedes hacerlo acá:\n"
                f"{PRIMARY_SOURCE_URL}"
            ),
        )
    if text in HELP_COMMANDS:
        return make_response(
            chat_id,
            canal,
            (
                "ℹ️ *Ayuda*\n\n"
                "BuscaChat te ayuda a consultar informacion sobre personas localizadas, "
                "desaparecidas o reportadas por fuentes de informacion.\n\n"
                "Fuente principal de informacion: https://venezuelatebusca.com/\n\n"
                "• Para buscar, escribe un nombre, una cédula o envia una foto.\n"
                f"• Para reportar a alguien, usa {PRIMARY_SOURCE_URL}\n"
            ),
            buttons=[MAIN_MENU_BUTTON],
        )
    if text in GREETINGS:
        return menu_response(chat_id, canal)
    if text:
        return _search_query_action(msg, chat_id, text, store)
    return menu_response(chat_id, canal)


def _handle_buscar_modo(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    if msg.get("imagen_ref"):
        return _handle_buscar_foto(msg, chat_id, store)
    if text in SEARCH_QUERY_COMMANDS:
        set_conversation_state(chat_id, {"paso": "buscar_query"}, store)
        return make_response(
            chat_id,
            canal,
            "Escribe el *numero de cédula* o *nombre* de la persona que buscas:",
        )
    if text in SEARCH_PHOTO_COMMANDS:
        set_conversation_state(chat_id, {"paso": "buscar_foto"}, store)
        return make_response(
            chat_id,
            canal,
            "Enviame una *foto clara del rostro* de la persona que buscas. 📷",
        )
    return make_response(
        chat_id,
        canal,
        "Elige *1* para buscar por cédula o nombre, o *2* para buscar por foto.",
        buttons=[
            ("1", "Buscar por cédula o nombre"),
            ("2", "Buscar por foto"),
        ],
    )


def _handle_buscar_query(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    if not text:
        return make_response(chat_id, canal, "Escribe un *numero de cédula* o *nombre* valido.")
    return _search_query_action(msg, chat_id, text, store)


def _handle_buscar_foto(
    msg: dict[str, Any],
    chat_id: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    set_conversation_state(chat_id, {"paso": "buscar_resultado", "tipo": "foto"}, store)
    return {
        "chat_id": chat_id,
        "canal": msg["canal"],
        "source": msg.get("source"),
        "respuesta": None,
        "accion": "buscar_por_foto",
        "datos": {},
        "imagen_ref": msg.get("imagen_ref"),
        "_embedding": msg.get("_embedding"),
        "sender": msg.get("sender"),
        "nombre": msg.get("nombre"),
    }


def _handle_buscar_cedula(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    return _search_query_action(msg, chat_id, text, store)


def _handle_buscar_nombre(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    return _search_query_action(msg, chat_id, text, store)


def _search_query_action(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    query = msg.get("text", "").strip() or text
    set_conversation_state(chat_id, {"paso": "buscar_resultado", "tipo": "query", "query": query}, store)
    return {
        "chat_id": chat_id,
        "canal": msg["canal"],
        "source": msg.get("source"),
        "respuesta": None,
        "accion": "buscar_por_query",
        "datos": {"query": query},
        "sender": msg.get("sender"),
        "nombre": msg.get("nombre"),
    }


def _handle_buscar_resultado(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    if text == MENU_COMMAND:
        set_conversation_state(chat_id, None, store)
        return menu_response(chat_id, canal)
    if text in ("buscar", "buscar persona", "volver a buscar", "1"):
        set_conversation_state(chat_id, {"paso": "buscar_modo"}, store)
        return search_mode_response(chat_id, canal)
    if text in MARK_FOUND_COMMANDS:
        state = get_conversation_state(chat_id, store)
        set_conversation_state(chat_id, None, store)
        return {
            "chat_id": chat_id,
            "canal": canal,
            "source": msg.get("source"),
            "respuesta": None,
            "accion": "marcar_encontrado",
            "datos": {
                "person_id": state.get("person_id"),
                "person_name": state.get("person_name"),
            },
            "sender": msg.get("sender"),
            "nombre": msg.get("nombre"),
        }
    set_conversation_state(chat_id, None, store)
    return menu_response(chat_id, canal)


def _handle_reg_nombre(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    if not text:
        return make_response(chat_id, canal, "Por favor escribe un nombre valido.")
    nombre = msg.get("text", "").strip()
    set_conversation_state(chat_id, {"paso": "reg_edad", "nombre": nombre}, store)
    return make_response(
        chat_id,
        canal,
        f"¿Que edad aproximada tiene *{nombre}*? Responde *omitir* si no lo sabes.",
    )


def _handle_reg_edad(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    state["edad"] = None if text in ("omitir", "no se", "no sé", "ns") else text
    state["paso"] = "reg_cedula"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        f"¿Tienes el numero de cédula de *{state['nombre']}*? Responde *omitir* si no lo tienes.",
    )


def _handle_reg_cedula(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    state["cedula"] = None if text in ("omitir", "no", "no se", "no sé", "ns") else text
    state["paso"] = "reg_ubicacion"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        f"¿Donde fue vista por ultima vez *{state['nombre']}*? Puedes incluir zona, calle, hospital o referencia.",
    )


def _handle_reg_ubicacion(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    state["ubicacion"] = None if text in ("omitir", "no se", "no sé", "ns") else (msg.get("text", "").strip() or None)
    state["paso"] = "reg_descripcion"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        (
            f"¿Como podrias describir a *{state['nombre']}*? "
            "Incluye ropa, estatura, señas particulares o informacion relevante. "
            "Escribe *omitir* para saltar."
        ),
    )


def _handle_reg_descripcion(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    state["descripcion"] = None if text in ("omitir", "no", "ns") else msg.get("text", "").strip()
    state["paso"] = "reg_foto"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        f"Enviame una *foto clara* de *{state['nombre']}*. Escribe *omitir* si no tienes una.",
    )


def _handle_reg_foto(
    msg: dict[str, Any],
    chat_id: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    text = msg.get("text", "").strip().casefold()

    if text in ("omitir", "no", "no tengo"):
        state["imagen_ref"] = None
        state.pop("_embedding", None)
        state["paso"] = "reg_contacto"
        set_conversation_state(chat_id, state, store)
        return make_response(
            chat_id,
            canal,
            f"¿Como podemos contactar a quien reporta a *{state['nombre']}*? Indica telefono u otro contacto.",
        )

    if msg.get("imagen_ref"):
        state["imagen_ref"] = msg["imagen_ref"]
        if msg.get("_embedding"):
            state["_embedding"] = msg["_embedding"]
        state["paso"] = "reg_contacto"
        set_conversation_state(chat_id, state, store)
        return make_response(
            chat_id,
            canal,
            (
                "✅ Foto recibida.\n\n"
                f"¿Como podemos contactar a quien reporta a *{state['nombre']}*? "
                "Indica telefono u otro contacto."
            ),
        )

    return make_response(chat_id, canal, "Por favor envia una foto como imagen 📷 o escribe *omitir*.")


def _handle_reg_contacto(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    contacto = msg.get("text", "").strip() or None
    state["contacto"] = contacto
    state["paso"] = "reg_confirmar"
    set_conversation_state(chat_id, state, store)

    resumen = f"Revisa la informacion antes de guardar:\n\n👤 Nombre: *{state['nombre']}*"
    if state.get("edad"):
        resumen += f"\n🎂 Edad aproximada: {state['edad']}"
    if state.get("cedula"):
        resumen += f"\n🪪 Cédula: {state['cedula']}"
    if state.get("ubicacion"):
        resumen += f"\n📍 Ultima ubicacion: {state['ubicacion']}"
    if state.get("descripcion"):
        resumen += f"\n📝 Descripcion: {state['descripcion']}"
    if state.get("imagen_ref"):
        resumen += "\n🖼 Foto: recibida"
    if contacto:
        resumen += f"\n📞 Contacto: {contacto}"
    resumen += "\n\n¿Confirmas el registro?"

    return make_response(chat_id, canal, resumen, buttons=[("si", "Confirmar"), ("no", "Cancelar")])


def _handle_reg_confirmar(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    embedding = state.get("_embedding")
    set_conversation_state(chat_id, None, store)
    if text in CONFIRM_COMMANDS:
        return {
            "chat_id": chat_id,
            "canal": canal,
            "source": msg.get("source"),
            "respuesta": None,
            "accion": "registrar_persona",
            "datos": {
                "nombre": state["nombre"],
                "edad": state.get("edad"),
                "cedula": state.get("cedula"),
                "ubicacion": state.get("ubicacion"),
                "descripcion": state.get("descripcion"),
                "contacto": state.get("contacto"),
            },
            "_embedding": embedding,
            "imagen_ref": state.get("imagen_ref"),
            "sender": msg.get("sender"),
            "nombre": msg.get("nombre", state["nombre"]),
        }
    return make_response(
        chat_id,
        canal,
        "Registro cancelado.",
        buttons=[MAIN_MENU_BUTTON],
    )
