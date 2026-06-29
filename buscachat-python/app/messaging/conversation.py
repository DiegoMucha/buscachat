from typing import Any

from app.messaging.session_store import (
    ConversationStateStore,
    get_default_conversation_state_store,
)


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
            "Enviame un mensaje para obtener informacion sobre personas localizadas, "
            "desaparecidas o fuentes de informacion disponibles.\n\n"
            "Puedo ayudarte a:\n"
            "Responde con el numero de la opcion."
            "para volver al inicio."
        ),
        buttons=[("1", "Buscar"), ("2", "Registrar"), ("3", "Ayuda")],
    )


def run_conversation_motor(
    msg: dict[str, Any],
    store: ConversationStateStore | None = None,
) -> dict[str, Any]:
    chat_id = msg["chat_id"]
    text = msg.get("text", "").strip().lower()

    if text in ("menu", "0", "cancelar", "salir", "inicio"):
        set_conversation_state(chat_id, {"paso": "menu"}, store)
        return menu_response(chat_id, msg["canal"])

    state = get_conversation_state(chat_id, store)
    paso = state.get("paso", "menu")

    if paso == "menu":
        return _handle_menu(msg, chat_id, text, store)
    if paso == "buscar_modo":
        return _handle_buscar_modo(msg, chat_id, text, store)
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
    if text == "1":
        set_conversation_state(chat_id, {"paso": "buscar_modo"}, store)
        return make_response(
            chat_id,
            canal,
            (
                "🔎 *Busqueda de persona*\n\n"
                "Elige como quieres buscar. Si tienes una foto clara del rostro, la busqueda "
                "por foto puede ayudar a encontrar coincidencias. Si no, tambien puedes buscar "
                "por nombre o cedula."
            ),
            buttons=[
                ("1", "Por foto"),
                ("2", "Por nombre"),
                ("3", "Por cedula"),
            ],
        )
    if text == "2":
        set_conversation_state(chat_id, {"paso": "reg_nombre"}, store)
        return make_response(
            chat_id,
            canal,
            "📝 *Registrar persona desaparecida*\n\nEscribe el *nombre completo* de la persona.",
        )
    if text == "3":
        return make_response(
            chat_id,
            canal,
            (
                "ℹ️ *Ayuda*\n\n"
                "BuscaChat te ayuda a consultar informacion sobre personas localizadas, "
                "desaparecidas o reportadas por fuentes de informacion.\n\n"
                "• Para buscar, puedes usar una foto, un nombre o una cedula.\n"
                "• Para registrar un caso, te pedire nombre, edad aproximada, ubicacion, "
                "descripcion, foto y contacto.\n"
                "• La informacion compartida debe usarse con cuidado y solo para apoyar la "
                "localizacion de personas.\n\n"
                "Escribe *menu* para volver al inicio."
            ),
        )
    return menu_response(chat_id, canal)


def _handle_buscar_modo(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    canal = msg["canal"]
    if text == "1":
        set_conversation_state(chat_id, {"paso": "buscar_foto"}, store)
        return make_response(
            chat_id,
            canal,
            "Enviame una *foto clara del rostro* de la persona que buscas. 📷",
        )
    if text == "2":
        set_conversation_state(chat_id, {"paso": "buscar_nombre"}, store)
        return make_response(
            chat_id,
            canal,
            "Escribe el *nombre o parte del nombre* de la persona que buscas:",
        )
    if text == "3":
        set_conversation_state(chat_id, {"paso": "buscar_cedula"}, store)
        return make_response(
            chat_id,
            canal,
            "Escribe el numero de *cedula* de la persona que buscas:",
        )
    return make_response(chat_id, canal, "Responde *1* por foto, *2* por nombre o *3* por cedula.")


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
    set_conversation_state(chat_id, {"paso": "buscar_resultado", "tipo": "cedula", "query": text}, store)
    return {
        "chat_id": chat_id,
        "canal": msg["canal"],
        "source": msg.get("source"),
        "respuesta": None,
        "accion": "buscar_por_cedula",
        "datos": {"query": text},
        "sender": msg.get("sender"),
        "nombre": msg.get("nombre"),
    }


def _handle_buscar_nombre(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    set_conversation_state(chat_id, {"paso": "buscar_resultado", "tipo": "nombre", "query": text}, store)
    return {
        "chat_id": chat_id,
        "canal": msg["canal"],
        "source": msg.get("source"),
        "respuesta": None,
        "accion": "buscar_por_nombre",
        "datos": {"query": text},
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
    if text in ("menu", "0", "cancelar", "salir", "inicio"):
        set_conversation_state(chat_id, None, store)
        return menu_response(chat_id, canal)
    if text in ("si", "sí", "yes", "ok", "marcar"):
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
        f"¿Tienes el numero de cedula de *{state['nombre']}*? Responde *omitir* si no lo tienes.",
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
    text = msg.get("text", "").strip().lower()

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
        resumen += f"\n🪪 Cedula: {state['cedula']}"
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
    if text in ("si", "sí", "yes", "ok"):
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
    return make_response(chat_id, canal, "Registro cancelado. Escribe *menu* para empezar de nuevo.")
