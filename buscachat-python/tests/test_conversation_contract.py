import pytest

from app.messaging.conversation import run_conversation_motor
from app.messaging.session_store import InMemoryConversationStateStore


def _message(text: str, chat_id: str = "chat-1") -> dict:
    return {
        "chat_id": chat_id,
        "canal": "meta",
        "text": text,
        "sender": "user-1",
        "nombre": "Example User",
    }


@pytest.mark.parametrize(
    ("text", "expected_text", "expected_step"),
    [
        ("Buscar", "Busqueda de persona", "buscar_modo"),
        ("Registrar", "Registrar persona desaparecida", "reg_nombre"),
        ("Ayuda", "Fuente principal de informacion", "menu"),
    ],
)
def test_main_menu_accepts_visible_button_labels(text: str, expected_text: str, expected_step: str) -> None:
    store = InMemoryConversationStateStore()
    store.set_state("chat-1", {"paso": "menu"})

    response = run_conversation_motor(_message(text), store=store)

    assert expected_text in response["respuesta"]
    assert store.get_state("chat-1")["paso"] == expected_step


@pytest.mark.parametrize("text", ["menu", "MENU", " Menu "])
def test_menu_is_the_only_global_shortcut(text: str) -> None:
    store = InMemoryConversationStateStore()
    store.set_state("chat-1", {"paso": "reg_edad", "nombre": "Example Person"})

    response = run_conversation_motor(_message(text), store=store)

    assert "BuscaChat" in response["respuesta"]
    assert store.get_state("chat-1")["paso"] == "menu"


@pytest.mark.parametrize("text", ["buscar", "volver a buscar", "Menu principal", "cancelar", "salir", "inicio", "0"])
def test_non_menu_shortcuts_do_not_bypass_current_flow(text: str) -> None:
    store = InMemoryConversationStateStore()
    store.set_state("chat-1", {"paso": "reg_edad", "nombre": "Example Person"})

    response = run_conversation_motor(_message(text), store=store)

    assert "numero de cédula" in response["respuesta"]
    assert store.get_state("chat-1")["paso"] == "reg_cedula"


@pytest.mark.parametrize(
    ("text", "expected_text", "expected_step"),
    [
        ("Buscar por cédula o nombre", "numero de cédula", "buscar_query"),
        ("Buscar por cedula o nombre", "numero de cédula", "buscar_query"),
        ("Buscar por foto", "busqueda por foto", "buscar_modo_foto"),
    ],
)
def test_search_mode_accepts_visible_button_labels(text: str, expected_text: str, expected_step: str) -> None:
    store = InMemoryConversationStateStore()
    store.set_state("chat-1", {"paso": "buscar_modo"})

    response = run_conversation_motor(_message(text), store=store)

    assert expected_text in response["respuesta"]
    assert store.get_state("chat-1")["paso"] == expected_step


@pytest.mark.parametrize("text", ["cedula", "cédula", "nombre", "por nombre", "foto", "por foto"])
def test_search_mode_rejects_unoffered_aliases(text: str) -> None:
    store = InMemoryConversationStateStore()
    store.set_state("chat-1", {"paso": "buscar_modo"})

    response = run_conversation_motor(_message(text), store=store)

    assert "Elige *1*" in response["respuesta"]
    assert store.get_state("chat-1")["paso"] == "buscar_modo"


def test_search_result_accepts_visible_mark_found_label() -> None:
    store = InMemoryConversationStateStore()
    store.set_state(
        "chat-1",
        {
            "paso": "buscar_resultado",
            "person_id": 123,
            "person_name": "Example Person",
        },
    )

    response = run_conversation_motor(_message("Marcar encontrada"), store=store)

    assert response["accion"] == "marcar_encontrado"
    assert response["datos"]["person_id"] == 123
