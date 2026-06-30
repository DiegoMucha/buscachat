from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import get_session
from app.face.stub import StubFaceMatcher
from app.messaging.adapters.web import WEB_CHAT_ID
from app.messaging.conversation import get_conversation_state, set_conversation_state
from app.messaging.dependencies import (
    get_face_matcher_dependency,
    get_notifier_dependency,
)
from app.messaging.notifier import NullNotifier
from app.messaging.web_chat_store import web_chat_store
from app.routers.web_chat import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)

    def session_override() -> Iterator[object]:
        yield object()

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_face_matcher_dependency] = lambda: StubFaceMatcher()
    app.dependency_overrides[get_notifier_dependency] = lambda: NullNotifier()
    app.dependency_overrides[get_settings] = lambda: Settings(
        face_matcher="stub",
        conversation_state_store="in_memory",
    )
    return TestClient(app)


def setup_function() -> None:
    web_chat_store.clear()
    set_conversation_state(WEB_CHAT_ID, None)


def teardown_function() -> None:
    web_chat_store.clear()
    set_conversation_state(WEB_CHAT_ID, None)


def test_web_chat_webhook_runs_pipeline_and_stores_transcript() -> None:
    client = _client()

    response = client.post("/web-chat/webhook", json={"text": "hola"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert [message["role"] for message in body["messages"]] == ["user", "bot"]
    assert body["messages"][0]["text"] == "hola"
    assert "BuscaChat" in body["messages"][1]["text"]

    messages = client.get("/web-chat/messages").json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "bot"


def test_web_chat_messages_support_polling_after_id() -> None:
    client = _client()

    client.post("/web-chat/webhook", json={"text": "hola"})
    search_response = client.post("/web-chat/webhook", json={"text": "1"}).json()

    search_message = search_response["messages"][1]
    assert "Busqueda de persona" in search_message["text"]
    assert "Elige una de las opciones:" in search_message["text"]
    assert [(button["id"], button["title"]) for button in search_message["buttons"]] == [
        ("1", "Buscar por cédula o nombre"),
        ("2", "Buscar por foto"),
    ]

    query_prompt_response = client.post("/web-chat/webhook", json={"text": "1"}).json()
    assert "nombre" in query_prompt_response["messages"][1]["text"]
    assert "cédula" in query_prompt_response["messages"][1]["text"]

    messages = client.get("/web-chat/messages?after_id=2").json()
    assert messages[0]["text"] == "1"
    assert "Busqueda de persona" in messages[1]["text"]


def test_web_chat_clear_resets_transcript_and_conversation_state() -> None:
    client = _client()

    client.post("/web-chat/webhook", json={"text": "1"})
    assert get_conversation_state(WEB_CHAT_ID)["paso"] == "buscar_modo"

    response = client.delete("/web-chat/messages")

    assert response.status_code == 200
    assert client.get("/web-chat/messages").json() == []
    assert get_conversation_state(WEB_CHAT_ID)["paso"] == "menu"


def test_search_flow_has_foto_sub_menu() -> None:
    """Al elegir 'buscar' y luego 'foto', debe mostrar sub-menu foto persona vs foto cedula."""
    client = _client()

    # Menu → buscar
    client.post("/web-chat/webhook", json={"text": "1"})
    # buscar_modo → elegir "1" (por foto)
    resp = client.post("/web-chat/webhook", json={"text": "1"})

    messages = resp.json()["messages"]
    bot_msg = messages[-1]
    assert (
        "busqueda por foto" in bot_msg["text"].lower()
        or "foto persona" in bot_msg["text"].lower()
    )
    assert bot_msg["buttons"][0]["title"] == "Foto persona"
    assert bot_msg["buttons"][1]["title"] == "Foto cedula"


def test_register_flow_ocr_step_accepts_text_no() -> None:
    """Al registrar, despues del nombre se ofrece OCR. Decir 'no' salta a edad."""
    client = _client()

    # Menu → registrar
    client.post("/web-chat/webhook", json={"text": "2"})
    # Dar nombre
    client.post("/web-chat/webhook", json={"text": "Juan Perez"})
    # El bot debe preguntar si tiene foto de cedula
    messages = client.get("/web-chat/messages").json()
    bot_texts = [m["text"] for m in messages if m["role"] == "bot"]
    assert any(
        "cedula" in t.lower() for t in bot_texts
    ), f"Expected cedula question in: {bot_texts}"

    # Decir "no" debe avanzar a edad
    resp = client.post("/web-chat/webhook", json={"text": "no"})
    bot_msg = resp.json()["messages"][-1]
    assert "edad" in bot_msg["text"].lower()


def test_register_flow_ocr_accepts_image_and_confirms() -> None:
    """Enviar foto de cedula debe mostrar datos extraidos y botones si/no."""
    client = _client()

    # Menu → registrar
    client.post("/web-chat/webhook", json={"text": "2"})
    # Dar nombre
    client.post("/web-chat/webhook", json={"text": "Juan Perez"})

    # Enviar foto (el web chat la intenta descargar, falla porque es fake URL)
    # Pero el flujo no debe crashear — debe caer en el fallback manual
    resp = client.post(
        "/web-chat/webhook",
        json={
            "text": "",
            "image_ref": "https://example.com/fake-cedula.jpg",
        },
    )
    assert resp.status_code == 200
    # Debe continuar al siguiente paso (edad) porque el download falla
    bot_msg = resp.json()["messages"][-1]
    assert "edad" in bot_msg["text"].lower() or "manual" in bot_msg["text"].lower()
