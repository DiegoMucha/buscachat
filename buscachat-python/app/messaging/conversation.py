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
        "BuscaChat - Bot de reunificacion familiar",
        buttons=[("1", "Buscar"), ("2", "Registrar")],
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
    if paso == "buscar_modo_foto":
        return _handle_buscar_modo_foto(msg, chat_id, text, store)
    if paso == "buscar_ocr":
        return _handle_buscar_ocr(msg, chat_id, store)
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
    if paso == "reg_cedula_ocr":
        return _handle_reg_cedula_ocr(msg, chat_id, store)
    if paso == "reg_ocr_confirmar":
        return _handle_reg_ocr_confirmar(msg, chat_id, text, store)
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
            chat_id, canal, "Como queres buscar?",
            buttons=[("1", "Por foto"), ("2", "Por nombre"), ("3", "Por cedula")],
        )
    if text == "2":
        set_conversation_state(chat_id, {"paso": "reg_nombre"}, store)
        return make_response(
            chat_id, canal, "Escribe el *nombre completo* de la persona desaparecida:"
        )
    if text == "3":
        return make_response(
            chat_id, canal,
            "BuscaChat te ayuda a encontrar personas desaparecidas. Escribe *menu* para volver.",

        )
    # Ayuda por texto libre
    return make_response(
        chat_id, canal,
        "BuscaChat — Bot de busqueda de desaparecidos. Opciones:\n1. Buscar\n2. Registrar\n3. Buscar por lista\nEscribe *ayuda* para mas info.",
    )
    return menu_response(chat_id, canal)


def _handle_buscar_modo(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    """Menú de búsqueda: foto, nombre o cédula."""
    canal = msg["canal"]
    if text == "1":
        set_conversation_state(chat_id, {"paso": "buscar_modo_foto"}, store)
        return make_response(
            chat_id, canal, "Que tipo de busqueda por foto?",
            buttons=[("1", "Foto persona"), ("2", "Foto cedula")],
        )
    if text == "2":
        set_conversation_state(chat_id, {"paso": "buscar_nombre"}, store)
        return make_response(chat_id, canal, "Escribe el *nombre* de la persona que buscas:")
    if text == "3":
        set_conversation_state(chat_id, {"paso": "buscar_cedula"}, store)
        return make_response(chat_id, canal, "Escribe el numero de *cedula* de la persona que buscas:")
    return make_response(chat_id, canal, "Usa los botones: *1* foto, *2* nombre, *3* cedula")


def _handle_buscar_modo_foto(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    """Sub-menú de búsqueda por foto: persona (facial) o cédula (OCR)."""
    canal = msg["canal"]
    if text == "1":
        set_conversation_state(chat_id, {"paso": "buscar_foto"}, store)
        return make_response(chat_id, canal, "Enviame la *foto* de la persona que buscas.")
    if text == "2":
        set_conversation_state(chat_id, {"paso": "buscar_ocr"}, store)
        return make_response(chat_id, canal, "Envia una *foto de la cedula* para buscar automaticamente.")
    return make_response(chat_id, canal, "Elegi *1* (foto persona) o *2* (foto cedula)")


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


def _handle_buscar_ocr(
    msg: dict[str, Any],
    chat_id: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    """Buscar persona escaneando foto de cedula con OCR."""
    canal = msg["canal"]
    if not msg.get("imagen_ref") or not msg.get("_image_bytes"):
        return make_response(chat_id, canal, "Por favor envia una foto de la cedula.")

    try:
        from app.services.ocr_service import extract_from_id_image
        ocr = extract_from_id_image(msg["_image_bytes"])
        nombre = ocr.get("nombre")
        cedula = ocr.get("cedula")
        if not nombre and not cedula:
            return make_response(chat_id, canal,
                "No se pudo leer la cedula. Intenta con otra foto o busca manualmente.")
        set_conversation_state(chat_id, None, store)
        return {
            "chat_id": chat_id, "canal": canal, "respuesta": None,
            "accion": "buscar_por_ocr",
            "datos": {"nombre_ocr": nombre, "cedula_ocr": cedula},
            "sender": msg.get("sender"), "nombre": msg.get("nombre"),
        }
    except ImportError:
        return make_response(chat_id, canal,
            "El servicio OCR no esta disponible. Busca manualmente por nombre o cedula.")
    except Exception:
        log.exception("OCR search failed")
        return make_response(chat_id, canal,
            "Error al procesar la cedula. Intenta buscar manualmente.")


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
    set_conversation_state(chat_id, {"paso": "reg_cedula_ocr", "nombre": nombre}, store)
    return make_response(
        chat_id, canal,
        f"Tenes una foto de la cedula de *{nombre}*? Enviala para rellenar los datos automaticamente, o escribe *no* para continuar manualmente."
    )


def _handle_reg_cedula_ocr(
    msg: dict[str, Any],
    chat_id: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    """Paso opcional: escanear cedula con OCR para rellenar datos."""
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)
    text = msg.get("text", "").strip().lower()

    if text in ("no", "omitir", "n", "no tengo", "ns"):
        state["paso"] = "reg_edad"
        set_conversation_state(chat_id, state, store)
        return make_response(chat_id, canal, f"Ok. Que edad tiene *{state['nombre']}*? (escribe *omitir* si no sabes)")

    if msg.get("imagen_ref") and msg.get("_image_bytes"):
        try:
            from app.services.ocr_service import extract_from_id_image
            ocr_data = extract_from_id_image(msg["_image_bytes"])
            if ocr_data.get("nombre"):
                state["nombre"] = ocr_data["nombre"]
            if ocr_data.get("cedula"):
                state["cedula"] = ocr_data["cedula"]
            state["_ocr_data"] = ocr_data

            resumen = f"*Datos detectados:*\nNombre: {state['nombre']}"
            if state.get("cedula"):
                resumen += f"\nCedula: {state['cedula']}"
            if ocr_data.get("fecha_nacimiento"):
                resumen += f"\nFecha nacimiento: {ocr_data['fecha_nacimiento']}"
            resumen += "\n\n*Es correcto?*"

            state["paso"] = "reg_ocr_confirmar"
            set_conversation_state(chat_id, state, store)
            return make_response(chat_id, canal, resumen, buttons=[("si", "Si"), ("no", "No")])
        except ImportError:
            log.warning("PaddleOCR not available, falling back to manual")
        except Exception:
            log.exception("OCR failed")

    state["paso"] = "reg_edad"
    set_conversation_state(chat_id, state, store)
    return make_response(chat_id, canal, f"Que edad tiene *{state['nombre']}*? (escribe *omitir* si no sabes)")


def _handle_reg_ocr_confirmar(
    msg: dict[str, Any],
    chat_id: str,
    text: str,
    store: ConversationStateStore | None,
) -> dict[str, Any]:
    """Confirma o rechaza los datos extraidos por OCR."""
    canal = msg["canal"]
    state = get_conversation_state(chat_id, store)

    if text in ("si", "yes", "ok"):
        # Datos confirmados, saltar a ubicacion (ya tenemos nombre y cedula)
        state["paso"] = "reg_ubicacion"
        set_conversation_state(chat_id, state, store)
        return make_response(chat_id, canal, f"Donde fue vista por ultima vez *{state['nombre']}*? (municipio, parroquia, hospital...)")
    else:
        # Rechazado, continuar manual desde edad
        state["paso"] = "reg_edad"
        set_conversation_state(chat_id, state, store)
        return make_response(chat_id, canal, f"Ok, empecemos de nuevo. Que edad tiene *{state['nombre']}*? (escribe *omitir* si no sabes)")


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
    return make_response(chat_id, canal, f"Tenes el numero de cedula de *{state['nombre']}*? (responde *omitir* si no)")


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
    return make_response(chat_id, canal, f"Donde fue vista por ultima vez *{state['nombre']}*?")


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
            f"Como podrias describir a *{state['nombre']}*? "
            "(ropa, estatura, senas particulares... escribe *omitir* para saltar)"
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
    return make_response(chat_id, canal, f"Enviame una *foto* de *{state['nombre']}*. (escribe *omitir* si no tenes)")


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
            f"Como podemos contactar a quien reporta a *{state['nombre']}*? (telefono)",
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
            f"Foto recibida. Como podemos contactar a quien reporta a *{state['nombre']}*? (telefono)",
        )

    return make_response(chat_id, canal, "Por favor envia una foto o escribe *omitir*.")


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


    """Separa texto en items (por newline, coma, punto y coma)."""
    import re
    items = re.split(r"[\n,;]+", raw)
    return [i.strip() for i in items if i.strip()]
