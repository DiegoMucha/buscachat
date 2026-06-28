import threading
from typing import Any

_state: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def get_conversation_state(chat_id: str) -> dict[str, Any]:
    with _lock:
        if chat_id not in _state:
            _state[chat_id] = {"paso": "menu"}
        return _state[chat_id]


def set_conversation_state(chat_id: str, data: dict[str, Any] | None) -> None:
    with _lock:
        if data is None:
            _state.pop(chat_id, None)
        else:
            _state[chat_id] = data


def save_embedding_for_chat(chat_id: str, embedding: list[float] | None) -> None:
    with _lock:
        state = _state.get(chat_id, {})
        if embedding:
            state["_embedding"] = list(embedding)
        else:
            state.pop("_embedding", None)
        _state[chat_id] = state


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
        "BuscaChat - Bot de reunificacion familiar",
        buttons=[("1", "Buscar"), ("2", "Registrar"), ("3", "Ayuda")],
    )


def run_conversation_motor(msg: dict[str, Any]) -> dict[str, Any]:
    chat_id = msg["chat_id"]
    text = msg.get("text", "").strip().lower()

    if text in ("menu", "0", "cancelar", "salir", "inicio"):
        set_conversation_state(chat_id, {"paso": "menu"})
        return menu_response(chat_id, msg["canal"])

    state = get_conversation_state(chat_id)
    paso = state.get("paso", "menu")

    if paso == "menu":
        return _handle_menu(msg, chat_id, text)
    if paso == "buscar_modo":
        return _handle_buscar_modo(msg, chat_id, text)
    if paso == "buscar_foto":
        return _handle_buscar_foto(msg, chat_id)
    if paso == "buscar_nombre":
        return _handle_buscar_nombre(msg, chat_id, text)
    if paso == "buscar_cedula":
        return _handle_buscar_cedula(msg, chat_id, text)
    if paso == "buscar_resultado":
        return _handle_buscar_resultado(msg, chat_id, text)
    if paso == "reg_nombre":
        return _handle_reg_nombre(msg, chat_id, text)
    if paso == "reg_edad":
        return _handle_reg_edad(msg, chat_id, text)
    if paso == "reg_cedula":
        return _handle_reg_cedula(msg, chat_id, text)
    if paso == "reg_ubicacion":
        return _handle_reg_ubicacion(msg, chat_id, text)
    if paso == "reg_descripcion":
        return _handle_reg_descripcion(msg, chat_id, text)
    if paso == "reg_foto":
        return _handle_reg_foto(msg, chat_id)
    if paso == "reg_contacto":
        return _handle_reg_contacto(msg, chat_id, text)
    if paso == "reg_confirmar":
        return _handle_reg_confirmar(msg, chat_id, text)

    return menu_response(chat_id, msg["canal"])


def _handle_menu(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    if text == "1":
        set_conversation_state(chat_id, {"paso": "buscar_modo"})
        return make_response(
            chat_id,
            canal,
            "Como queres buscar?",
            buttons=[
                ("1", "Por foto"),
                ("2", "Por nombre"),
                ("3", "Por cedula"),
            ],
        )
    if text == "2":
        set_conversation_state(chat_id, {"paso": "reg_nombre"})
        return make_response(
            chat_id, canal, "Escribe el *nombre completo* de la persona desaparecida:"
        )
    if text == "3":
        return make_response(
            chat_id,
            canal,
            "BuscaChat te ayuda a encontrar personas desaparecidas. Escribe *menu* para volver al inicio.",
        )
    return menu_response(chat_id, canal)


def _handle_buscar_modo(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    if text == "1":
        set_conversation_state(chat_id, {"paso": "buscar_foto"})
        return make_response(chat_id, canal, "Enviame la *foto* de la persona que buscas.")
    if text == "2":
        set_conversation_state(chat_id, {"paso": "buscar_nombre"})
        return make_response(chat_id, canal, "Escribe el *nombre* de la persona que buscas:")
    if text == "3":
        set_conversation_state(chat_id, {"paso": "buscar_cedula"})
        return make_response(chat_id, canal, "Escribe el numero de *cedula* de la persona que buscas:")
    return make_response(chat_id, canal, "Responde *1* (foto), *2* (nombre) o *3* (cedula)")


def _handle_buscar_foto(msg: dict[str, Any], chat_id: str) -> dict[str, Any]:
    set_conversation_state(chat_id, {"paso": "buscar_resultado", "tipo": "foto"})
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


def _handle_buscar_cedula(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    set_conversation_state(chat_id, {"paso": "buscar_resultado", "tipo": "cedula", "query": text})
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


def _handle_buscar_nombre(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    set_conversation_state(chat_id, {"paso": "buscar_resultado", "tipo": "nombre", "query": text})
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


def _handle_buscar_resultado(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    if text in ("menu", "0", "cancelar", "salir", "inicio"):
        set_conversation_state(chat_id, None)
        return menu_response(chat_id, canal)
    if text in ("si", "sí", "yes", "ok", "marcar"):
        state = get_conversation_state(chat_id)
        set_conversation_state(chat_id, None)
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
    set_conversation_state(chat_id, None)
    return menu_response(chat_id, canal)


def _handle_reg_nombre(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    if not text:
        return make_response(chat_id, canal, "Por favor escribe un nombre valido.")
    nombre = msg.get("text", "").strip()
    set_conversation_state(chat_id, {"paso": "reg_edad", "nombre": nombre})
    return make_response(chat_id, canal, f"Que edad tiene *{nombre}*? (responde *omitir* si no sabes)")


def _handle_reg_edad(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    state["edad"] = None if text in ("omitir", "no se", "no sé", "ns") else text
    state["paso"] = "reg_cedula"
    set_conversation_state(chat_id, state)
    return make_response(chat_id, canal, f"Tenes el numero de cedula de *{state['nombre']}*? (responde *omitir* si no)")


def _handle_reg_cedula(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    state["cedula"] = None if text in ("omitir", "no", "no se", "no sé", "ns") else text
    state["paso"] = "reg_ubicacion"
    set_conversation_state(chat_id, state)
    return make_response(chat_id, canal, f"Donde fue vista por ultima vez *{state['nombre']}*?")


def _handle_reg_ubicacion(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    state["ubicacion"] = None if text in ("omitir", "no se", "no sé", "ns") else (msg.get("text", "").strip() or None)
    state["paso"] = "reg_descripcion"
    set_conversation_state(chat_id, state)
    return make_response(chat_id, canal, f"Como podrias describir a *{state['nombre']}*? (ropa, estatura, senas particulares... escribe *omitir* para saltar)")


def _handle_reg_descripcion(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    state["descripcion"] = None if text in ("omitir", "no", "ns") else msg.get("text", "").strip()
    state["paso"] = "reg_foto"
    set_conversation_state(chat_id, state)
    return make_response(chat_id, canal, f"Enviame una *foto* de *{state['nombre']}*. (escribe *omitir* si no tenes)")


def _handle_reg_foto(msg: dict[str, Any], chat_id: str) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    text = msg.get("text", "").strip().lower()

    if text in ("omitir", "no", "no tengo"):
        state["imagen_ref"] = None
        state.pop("_embedding", None)
        state["paso"] = "reg_contacto"
        set_conversation_state(chat_id, state)
        return make_response(chat_id, canal, f"Como podemos contactar a quien reporta a *{state['nombre']}*? (telefono)")

    if msg.get("imagen_ref"):
        state["imagen_ref"] = msg["imagen_ref"]
        if msg.get("_embedding"):
            state["_embedding"] = msg["_embedding"]
        state["paso"] = "reg_contacto"
        set_conversation_state(chat_id, state)
        return make_response(chat_id, canal, f"Foto recibida. Como podemos contactar a quien reporta a *{state['nombre']}*? (telefono)")

    return make_response(chat_id, canal, "Por favor envia una foto o escribe *omitir*.")


def _handle_reg_contacto(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    contacto = msg.get("text", "").strip() or None
    state["contacto"] = contacto
    state["paso"] = "reg_confirmar"
    set_conversation_state(chat_id, state)

    resumen = f"*{state['nombre']}*"
    if state.get("edad"):
        resumen += f"\nEdad: {state['edad']}"
    if state.get("cedula"):
        resumen += f"\nCedula: {state['cedula']}"
    if state.get("ubicacion"):
        resumen += f"\nUbicacion: {state['ubicacion']}"
    if state.get("descripcion"):
        resumen += f"\nDescripcion: {state['descripcion']}"
    if state.get("imagen_ref"):
        resumen += "\nFoto: recibida"
    if contacto:
        resumen += f"\nContacto: {contacto}"

    return make_response(chat_id, canal, resumen, buttons=[("si", "Confirmar"), ("no", "Cancelar")])


def _handle_reg_confirmar(msg: dict[str, Any], chat_id: str, text: str) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    embedding = state.get("_embedding")
    set_conversation_state(chat_id, None)
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
