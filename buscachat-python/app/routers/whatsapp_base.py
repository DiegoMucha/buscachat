"""Base compartida para webhooks de WhatsApp (Green API y Meta).

Contiene: estado conversacional, motor de diálogo, dependencias cacheadas.
No registra rutas de FastAPI.
"""

import logging
import threading
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends

from app.adapters.green_api import Notifier, get_notifier
from app.config import Settings, get_settings
from app.face import FaceMatcher, get_face_matcher

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dependencias cacheadas
# ---------------------------------------------------------------------------


@lru_cache
def _cached_face_matcher() -> FaceMatcher:
    return get_face_matcher(get_settings())


def get_face_matcher_dep() -> FaceMatcher:
    return _cached_face_matcher()


def get_notifier_dep(settings: Annotated[Settings, Depends(get_settings)]) -> Notifier:
    return get_notifier(settings)


# ---------------------------------------------------------------------------
# Estado conversacional en memoria (chat_id → { paso, datos })
# ---------------------------------------------------------------------------
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
    """Guarda el embedding facial en el estado del chat."""
    with _lock:
        state = _state.get(chat_id, {})
        if embedding:
            state["_embedding"] = list(embedding)
        else:
            state.pop("_embedding", None)
        _state[chat_id] = state


def get_embedding_for_chat(chat_id: str) -> list[float] | None:
    """Recupera el embedding guardado del chat."""
    with _lock:
        return _state.get(chat_id, {}).get("_embedding")


# ---------------------------------------------------------------------------
# Helpers de respuesta
# ---------------------------------------------------------------------------


def make_response(chat_id: str, canal: str, text: str, accion: str | None = None, buttons: list[tuple[str, str]] | None = None) -> dict:
    out: dict = {"chat_id": chat_id, "canal": canal, "respuesta": text, "accion": accion}
    if buttons:
        out["buttons"] = buttons
    return out


def menu_response(chat_id: str, canal: str) -> dict:
    return make_response(
        chat_id, canal,
        "🤖 *BuscaChat* — Bot de reunificación familiar",
        buttons=[("1", "Buscar"), ("2", "Registrar"), ("3", "Ayuda")],
    )


# ---------------------------------------------------------------------------
# Motor conversacional
# ---------------------------------------------------------------------------


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


# -- Menú --


def _handle_menu(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    if text == "1":
        set_conversation_state(chat_id, {"paso": "buscar_modo"})
        return make_response(chat_id, canal, "¿Cómo querés buscar?",
                             buttons=[("1", "📸 Por foto"), ("2", "📝 Por nombre")])
    if text == "2":
        set_conversation_state(chat_id, {"paso": "reg_nombre"})
        return make_response(chat_id, canal, "Escribí el *nombre completo* de la persona desaparecida:")
    if text == "3":
        return make_response(chat_id, canal,
                             "BuscaChat te ayuda a encontrar personas desaparecidas tras el terremoto. Escribí *menu* para volver al inicio.")
    return menu_response(chat_id, canal)


# -- Buscar --


def _handle_buscar_modo(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    if text == "1":
        set_conversation_state(chat_id, {"paso": "buscar_foto"})
        return make_response(chat_id, canal, "Enviame la *foto* de la persona que buscás.")
    if text == "2":
        set_conversation_state(chat_id, {"paso": "buscar_nombre"})
        return make_response(chat_id, canal, "Escribí el *nombre* de la persona que buscás:")
    return make_response(chat_id, canal, "Respondé *1* (foto) o *2* (nombre)")


def _handle_buscar_foto(msg: dict, chat_id: str) -> dict:
    set_conversation_state(chat_id, None)
    return {
        "chat_id": chat_id, "canal": msg["canal"], "respuesta": None,
        "accion": "buscar_por_foto", "datos": {},
        "imagen_ref": msg.get("imagen_ref"),
        "sender": msg.get("sender"), "nombre": msg.get("nombre"),
    }


def _handle_buscar_nombre(msg: dict, chat_id: str, text: str) -> dict:
    set_conversation_state(chat_id, None)
    return {
        "chat_id": chat_id, "canal": msg["canal"], "respuesta": None,
        "accion": "buscar_por_nombre", "datos": {"query": text},
        "sender": msg.get("sender"), "nombre": msg.get("nombre"),
    }


# -- Registrar --


def _handle_reg_nombre(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    if not text:
        return make_response(chat_id, canal, "Por favor escribí un nombre válido.")
    nombre = msg.get("text", "").strip()
    set_conversation_state(chat_id, {"paso": "reg_edad", "nombre": nombre})
    return make_response(chat_id, canal, f"¿Qué edad tiene *{nombre}*? (respondé *omitir* si no sabés)")


def _handle_reg_edad(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    edad = None if text in ("omitir", "no se", "no sé", "ns") else text
    state["edad"] = edad
    state["paso"] = "reg_cedula"
    set_conversation_state(chat_id, state)
    return make_response(chat_id, canal, f"¿Tenés el número de cédula de *{state['nombre']}*? (respondé *omitir* si no)")


def _handle_reg_cedula(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    cedula = None if text in ("omitir", "no", "no se", "no sé", "ns") else text
    state["cedula"] = cedula
    state["paso"] = "reg_ubicacion"
    set_conversation_state(chat_id, state)
    return make_response(chat_id, canal, f"¿Dónde fue vista por última vez *{state['nombre']}*? (municipio, parroquia, sector, hospital...)")


def _handle_reg_ubicacion(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    ubicacion = None if text in ("omitir", "no se", "no sé", "ns") else (msg.get("text", "").strip() or None)
    state["ubicacion"] = ubicacion
    state["paso"] = "reg_descripcion"
    set_conversation_state(chat_id, state)
    return make_response(chat_id, canal, f"¿Cómo podrías describir a *{state['nombre']}*? (ropa, estatura, señas particulares... escribí *omitir* para saltar)")


def _handle_reg_descripcion(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    desc = None if text in ("omitir", "no", "ns") else msg.get("text", "").strip()
    state["descripcion"] = desc
    state["paso"] = "reg_foto"
    set_conversation_state(chat_id, state)
    return make_response(chat_id, canal, f"📸 Enviame una *foto* de *{state['nombre']}* para ayudar a identificarla. (escribí *omitir* si no tenés)")


def _handle_reg_foto(msg: dict, chat_id: str) -> dict:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    text = msg.get("text", "").strip().lower()

    if text in ("omitir", "no", "no tengo"):
        state["imagen_ref"] = None
        state["paso"] = "reg_contacto"
        set_conversation_state(chat_id, state)
        return make_response(chat_id, canal, f"¿Cómo podemos contactar a quien reporta a *{state['nombre']}*? (teléfono)")

    if msg.get("imagen_ref"):
        state["imagen_ref"] = msg["imagen_ref"]
        state["paso"] = "reg_contacto"
        set_conversation_state(chat_id, state)
        return make_response(chat_id, canal, f"✅ Foto recibida. ¿Cómo podemos contactar a quien reporta a *{state['nombre']}*? (teléfono)")

    return make_response(chat_id, canal, "Por favor enviá una foto o escribí *omitir*.")


def _handle_reg_contacto(msg: dict, chat_id: str, text: str) -> dict:
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
        resumen += f"\nCédula: {state['cedula']}"
    if state.get("ubicacion"):
        resumen += f"\nUbicación: {state['ubicacion']}"
    if state.get("descripcion"):
        resumen += f"\nDescripción: {state['descripcion']}"
    if state.get("imagen_ref"):
        resumen += "\n📸 Foto: ✅"
    if contacto:
        resumen += f"\nContacto: {contacto}"

    return make_response(chat_id, canal, resumen,
                         buttons=[("si", "✅ Confirmar"), ("no", "❌ Cancelar")])


def _handle_reg_confirmar(msg: dict, chat_id: str, text: str) -> dict:
    canal = msg["canal"]
    state = get_conversation_state(chat_id)
    _embedding = state.get("_embedding")
    set_conversation_state(chat_id, None)
    if text in ("si", "sí", "yes", "ok"):
        return {
            "chat_id": chat_id, "canal": canal, "respuesta": None,
            "accion": "registrar_persona",
            "datos": {
                "nombre": state["nombre"], "edad": state.get("edad"),
                "cedula": state.get("cedula"), "ubicacion": state.get("ubicacion"),
                "descripcion": state.get("descripcion"), "contacto": state.get("contacto"),
            },
            "_embedding": _embedding,
            "imagen_ref": state.get("imagen_ref"),
            "sender": msg.get("sender"), "nombre": msg.get("nombre", state["nombre"]),
        }
    return make_response(chat_id, canal, "Registro cancelado. Escribí *menu* para empezar de nuevo.")
