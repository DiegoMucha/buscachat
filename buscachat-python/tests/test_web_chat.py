from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.green_api import NullNotifier
from app.config import Settings, get_settings
from app.database import get_session
from app.face.stub import StubFaceMatcher
from app.messaging.adapters.web import WEB_CHAT_ID
from app.messaging.conversation import get_conversation_state, set_conversation_state
from app.messaging.dependencies import (
    get_face_matcher_dependency,
    get_notifier_dependency,
)
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
        notifier="null",
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
