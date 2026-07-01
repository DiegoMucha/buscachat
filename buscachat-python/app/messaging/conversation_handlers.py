"""Handlers del motor conversacional.

Importados lazy por ``conversation.py`` para evitar circular imports.
"""

import logging
from typing import Any

from app.messaging.conversation import (
    CONFIRM_COMMANDS,
    GREETINGS,
    HELP_COMMANDS,
    MAIN_MENU_BUTTON,
    PRIMARY_SOURCE_URL,
    REGISTER_COMMANDS,
    SEARCH_PERSON_COMMANDS,
    SEARCH_PHOTO_COMMANDS,
    SEARCH_QUERY_COMMANDS,
    get_conversation_state,
    make_response,
    menu_response,
    search_mode_response,
    set_conversation_state,
)
from app.messaging.session_store import ConversationStateStore

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------


def handle_menu(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    if text in SEARCH_PERSON_COMMANDS:
        set_conversation_state(chat_id, {"paso": "buscar_modo"}, store)
        return search_mode_response(chat_id, canal)
    if text in REGISTER_COMMANDS:
        # El boton visible "Registrar persona" muestra la URL.
        # Los comandos internos "2" y "registrar" inician el flujo de registro.
        if text in ("2", "registrar"):
            set_conversation_state(chat_id, {"paso": "reg_nombre"}, store)
            return make_response(
                chat_id,
                canal,
                "📝 *Registrar persona desaparecida*\n\nEscribe el *nombre completo* de la persona.",
            )
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


# ---------------------------------------------------------------------------
# Buscar
# ---------------------------------------------------------------------------


def handle_buscar_modo(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    if msg.get("imagen_ref"):
        return handle_buscar_foto(msg, chat_id, store)
    if text in SEARCH_QUERY_COMMANDS:
        set_conversation_state(chat_id, {"paso": "buscar_query"}, store)
        return make_response(
            chat_id,
            canal,
            "Escribe el *numero de cédula* o *nombre* de la persona que buscas:",
        )
    if text in SEARCH_PHOTO_COMMANDS:
        set_conversation_state(chat_id, {"paso": "buscar_modo_foto"}, store)
        return make_response(
            chat_id,
            canal,
            "¿Que tipo de busqueda por foto?",
            buttons=[("1", "Foto del rostro"), ("2", "Foto de cedula")],
        )
    return make_response(
        chat_id,
        canal,
        "Elige *1* para buscar por cédula o nombre, o *2* para buscar por foto.",
        buttons=[("1", "Buscar por cédula o nombre"), ("2", "Buscar por foto")],
    )


def handle_buscar_modo_foto(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    if msg.get("imagen_ref"):
        set_conversation_state(chat_id, {"paso": "buscar_foto"}, store)
        return handle_buscar_foto(msg, chat_id, store)
    if text in ("1", "rostro", "foto rostro"):
        set_conversation_state(chat_id, {"paso": "buscar_foto"}, store)
        return make_response(
            chat_id,
            canal,
            "Enviame una *foto clara del rostro* de la persona que buscas. 📷",
        )
    if text in ("2", "cedula", "cédula", "foto cedula"):
        set_conversation_state(chat_id, {"paso": "buscar_ocr"}, store)
        return make_response(
            chat_id, canal, "Envia una *foto de la cedula* para buscar automaticamente."
        )
    return make_response(chat_id, canal, "Elegi *1* (foto rostro) o *2* (foto cedula)")


def handle_buscar_query(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    if not text:
        return make_response(
            chat_id, canal, "Escribe un *numero de cédula* o *nombre* valido."
        )
    return _search_query_action(msg, chat_id, text, store)


def handle_buscar_foto(
    msg: dict[str, Any], chat_id: str, store: ConversationStateStore | None
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


def handle_buscar_nombre(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    set_conversation_state(
        chat_id, {"paso": "buscar_resultado", "tipo": "nombre", "query": text}, store
    )
    return {
        "chat_id": chat_id,
        "canal": msg["canal"],
        "source": msg.get("source"),
        "respuesta": None,
        "accion": "buscar_por_query",
        "datos": {"query": text},
        "sender": msg.get("sender"),
        "nombre": msg.get("nombre"),
    }


def handle_buscar_cedula(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    set_conversation_state(
        chat_id, {"paso": "buscar_resultado", "tipo": "cedula", "query": text}, store
    )
    return {
        "chat_id": chat_id,
        "canal": msg["canal"],
        "source": msg.get("source"),
        "respuesta": None,
        "accion": "buscar_por_query",
        "datos": {"query": text},
        "sender": msg.get("sender"),
        "nombre": msg.get("nombre"),
    }


def handle_buscar_resultado(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    from app.messaging.conversation import MARK_FOUND_COMMANDS

    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    if text in ("menu", "cancelar", "salir", "inicio"):
        set_conversation_state(chat_id, None, store)
        return menu_response(chat_id, canal)
    if text in ("buscar", "volver a buscar"):
        set_conversation_state(chat_id, {"paso": "buscar_modo"}, store)
        return search_mode_response(chat_id, canal)
    if text in ("registrar",):
        set_conversation_state(chat_id, {"paso": "reg_nombre"}, store)
        return make_response(
            chat_id,
            canal,
            "📝 *Registrar persona desaparecida*\n\nEscribe el *nombre completo* de la persona.",
        )
    if text in MARK_FOUND_COMMANDS and state.get("person_id"):
        return {
            "chat_id": chat_id,
            "canal": canal,
            "respuesta": None,
            "accion": "marcar_encontrado",
            "datos": {
                "person_id": state["person_id"],
                "person_name": state.get("person_name"),
            },
            "sender": msg.get("sender"),
            "nombre": msg.get("nombre"),
        }
    set_conversation_state(chat_id, None, store)
    return menu_response(chat_id, canal)


def handle_buscar_ocr(
    msg: dict[str, Any], chat_id: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    image_bytes = msg.get("_image_bytes")
    if not image_bytes:
        return make_response(
            chat_id,
            canal,
            (
                "Por favor envia una foto de la cedula."
                if not msg.get("imagen_ref")
                else "Procesando la imagen..."
            ),
        )
    try:
        from app.services.ocr_service import extract_from_id_image

        ocr = extract_from_id_image(image_bytes)
        nombre = ocr.get("nombre")
        cedula = ocr.get("cedula")
        if not nombre and not cedula:
            return make_response(
                chat_id,
                canal,
                "No se pudo leer la cedula. Intenta con otra foto o busca manualmente.",
            )
        set_conversation_state(chat_id, None, store)
        return {
            "chat_id": chat_id,
            "canal": canal,
            "respuesta": None,
            "accion": "buscar_por_ocr",
            "datos": {"nombre_ocr": nombre, "cedula_ocr": cedula},
            "sender": msg.get("sender"),
            "nombre": msg.get("nombre"),
        }
    except ImportError:
        return make_response(chat_id, canal, "OCR no disponible. Busca manualmente.")
    except Exception:
        return make_response(
            chat_id, canal, "Error al procesar la cedula. Intenta manualmente."
        )


# ---------------------------------------------------------------------------
# Registrar
# ---------------------------------------------------------------------------


def handle_reg_nombre(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    if not text:
        return make_response(chat_id, canal, "Por favor escribe un nombre valido.")
    nombre = msg.get("text", "").strip()
    set_conversation_state(chat_id, {"paso": "reg_cedula_ocr", "nombre": nombre}, store)
    return make_response(
        chat_id,
        canal,
        f"¿Tienes una foto de la cedula de *{nombre}*? Enviala para rellenar los datos, o escribe *no* para continuar.",
    )


def handle_reg_cedula_ocr(
    msg: dict[str, Any], chat_id: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    text = msg.get("text", "").strip().lower()
    if text in ("no", "omitir", "n", "no tengo", "ns"):
        state["paso"] = "reg_edad"
        set_conversation_state(chat_id, state, store)
        return make_response(
            chat_id,
            canal,
            f"Ok. ¿Que edad aproximada tiene *{state['nombre']}*? Responde *omitir* si no lo sabes.",
        )
    if msg.get("_image_bytes"):
        try:
            from app.services.ocr_service import extract_from_id_image

            ocr_data = extract_from_id_image(msg["_image_bytes"])
            if ocr_data.get("nombre") or ocr_data.get("cedula"):
                state["_nombre_original"] = state["nombre"]
                if ocr_data.get("nombre"):
                    state["nombre"] = ocr_data["nombre"]
                if ocr_data.get("cedula"):
                    state["cedula"] = ocr_data["cedula"]
                state["_ocr_data"] = ocr_data
                state["paso"] = "reg_ocr_confirmar"
                set_conversation_state(chat_id, state, store)
                resumen = f"*Datos detectados:*\nNombre: {state['nombre']}"
                if state.get("cedula"):
                    resumen += f"\nCedula: {state['cedula']}"
                if ocr_data.get("fecha_nacimiento"):
                    resumen += f"\nFecha nacimiento: {ocr_data['fecha_nacimiento']}"
                resumen += "\n\n*¿Es correcto?*"
                return make_response(chat_id, canal, resumen, buttons=[("si", "Si"), ("no", "No")])
        except ImportError:
            pass
        except Exception:
            pass
    state["paso"] = "reg_edad"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        f"¿Que edad aproximada tiene *{state['nombre']}*? Responde *omitir* si no lo sabes.",
    )


def handle_reg_ocr_confirmar(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    if text in ("si", "yes", "ok"):
        state["paso"] = "reg_ubicacion"
        set_conversation_state(chat_id, state, store)
        return make_response(
            chat_id, canal, f"¿Donde fue vista por ultima vez *{state['nombre']}*?"
        )
    state["nombre"] = state.get("_nombre_original", state["nombre"])
    state["paso"] = "reg_edad"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        f"Ok, usamos el nombre que escribiste. "
        f"¿Que edad aproximada tiene *{state['nombre']}*? "
        f"Responde *omitir* si no lo sabes.",
    )


def handle_reg_edad(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    state["edad"] = None if text in ("omitir", "no se", "no sé", "ns") else text
    state["paso"] = "reg_cedula"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        f"¿Tenés el numero de cédula de *{state['nombre']}*? Responde *omitir* si no.",
    )


def handle_reg_cedula(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    state["cedula"] = None if text in ("omitir", "no", "no se", "no sé", "ns") else text
    state["paso"] = "reg_ubicacion"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        f"¿Donde fue vista por ultima vez *{state['nombre']}*? (municipio, parroquia, hospital...)",
    )


def handle_reg_ubicacion(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    state["ubicacion"] = (
        None
        if text in ("omitir", "no se", "no sé", "ns")
        else (msg.get("text", "").strip() or None)
    )
    state["paso"] = "reg_descripcion"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        f"¿Como podrias describir a *{state['nombre']}*? Escribe *omitir* para saltar.",
    )


def handle_reg_descripcion(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    state["descripcion"] = (
        None if text in ("omitir", "no", "ns") else msg.get("text", "").strip()
    )
    state["paso"] = "reg_foto"
    set_conversation_state(chat_id, state, store)
    return make_response(
        chat_id,
        canal,
        f"📸 Envia una *foto* de *{state['nombre']}* para ayudar a identificarla. Escribe *omitir* si no tenes.",
    )


def handle_reg_foto(
    msg: dict[str, Any], chat_id: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    text = msg.get("text", "").strip().lower()
    if text in ("omitir", "no", "no tengo"):
        state["imagen_ref"] = None
        state["paso"] = "reg_contacto"
        set_conversation_state(chat_id, state, store)
        return make_response(
            chat_id,
            canal,
            f"¿Como podemos contactar a quien reporta a *{state['nombre']}*? (telefono)",
        )
    if msg.get("imagen_ref"):
        state["imagen_ref"] = msg["imagen_ref"]
        state["paso"] = "reg_contacto"
        set_conversation_state(chat_id, state, store)
        return make_response(
            chat_id,
            canal,
            "✅ Foto recibida. ¿Como podemos contactar a quien reporta?",
        )
    return make_response(chat_id, canal, "Por favor envia una foto o escribe *omitir*.")


def handle_reg_contacto(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    state["contacto"] = msg.get("text", "").strip() or None
    state["paso"] = "reg_confirmar"
    set_conversation_state(chat_id, state, store)
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
        resumen += "\n📸 Foto: ✅"
    if state.get("contacto"):
        resumen += f"\nContacto: {state['contacto']}"
    return make_response(
        chat_id, canal, resumen, buttons=[("si", "Confirmar"), ("no", "Cancelar")]
    )


def handle_reg_confirmar(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    embedding = state.get("_embedding")
    set_conversation_state(chat_id, None, store)
    if text in CONFIRM_COMMANDS:
        return {
            "chat_id": chat_id,
            "canal": canal,
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
        chat_id, canal, "Registro cancelado.", buttons=[("menu", "Menu principal")]
    )


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _search_query_action(
    msg: dict[str, Any], chat_id: str, text: str, store: ConversationStateStore | None
) -> dict[str, Any]:
    """Detecta si el texto es cedula o nombre y emite la accion correspondiente."""
    from app.services.search import _looks_like_cedula

    if _looks_like_cedula(text):
        return handle_buscar_cedula(msg, chat_id, text, store)
    return handle_buscar_nombre(msg, chat_id, text, store)
