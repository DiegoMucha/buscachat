import hashlib
import hmac
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.database import get_session
from app.messaging.dependencies import (
    get_conversation_state_store_dependency,
    get_face_matcher_dependency,
    get_notifier_dependency,
)
from app.messaging.types import Button
from app.routers import whatsapp_meta_webhook
from app.routers.whatsapp_meta_webhook import (
    META_BUTTON_ID_LIMIT,
    META_BUTTON_TITLE_LIMIT,
    _meta_interactive_payload,
    _send_meta_message,
    _verify_meta_signature,
    router,
)


def _app_with_meta_settings(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = lambda: object()
    app.dependency_overrides[get_face_matcher_dependency] = lambda: object()
    app.dependency_overrides[get_notifier_dependency] = lambda: object()
    app.dependency_overrides[get_conversation_state_store_dependency] = lambda: object()
    return app


def _meta_signature(raw_body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _meta_text_payload(message_id: str = "wamid.example") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"profile": {"name": "Example Sender"}, "wa_id": "15551234567"}],
                            "messages": [
                                {
                                    "from": "15551234567",
                                    "id": message_id,
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def test_meta_webhook_verification_echoes_challenge() -> None:
    app = _app_with_meta_settings(Settings(meta_verify_token="verify-me"))

    client = TestClient(app)
    response = client.get(
        "/whatsapp-meta-webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge-123"
    assert response.headers["content-type"].startswith("text/plain")


def test_meta_webhook_verification_rejects_wrong_token() -> None:
    app = _app_with_meta_settings(Settings(meta_verify_token="verify-me"))

    client = TestClient(app)
    response = client.get(
        "/whatsapp-meta-webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge-123",
        },
    )

    assert response.status_code == 403
    assert response.text == "Verification failed"


def test_meta_signature_verification_accepts_valid_signature() -> None:
    raw_body = b'{"entry":[]}'
    signature = _meta_signature(raw_body, "app-secret")

    assert _verify_meta_signature(raw_body, signature, "app-secret") is True


def test_meta_signature_verification_rejects_invalid_signature() -> None:
    raw_body = b'{"entry":[]}'

    assert _verify_meta_signature(raw_body, "sha256=bad", "app-secret") is False


def test_meta_signature_verification_is_disabled_without_app_secret() -> None:
    raw_body = b'{"entry":[]}'

    assert _verify_meta_signature(raw_body, None, "") is True


def test_meta_webhook_post_rejects_invalid_signature() -> None:
    app = _app_with_meta_settings(Settings(meta_verify_token="verify-me", meta_app_secret="app-secret"))
    client = TestClient(app)

    response = client.post(
        "/whatsapp-meta-webhook",
        content=b'{"entry":[]}',
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": "sha256=bad",
        },
    )

    assert response.status_code == 403
    assert response.text == "Invalid signature"


def test_meta_webhook_post_accepts_valid_signed_status_payload() -> None:
    app = _app_with_meta_settings(Settings(meta_verify_token="verify-me", meta_app_secret="app-secret"))
    client = TestClient(app)
    raw_body = json.dumps({"entry": [{"changes": [{"value": {"statuses": []}}]}]}).encode("utf-8")

    response = client.post(
        "/whatsapp-meta-webhook",
        content=raw_body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": _meta_signature(raw_body, "app-secret"),
        },
    )

    assert response.status_code == 200
    assert response.text == "ok"


def test_meta_webhook_post_acknowledges_and_schedules_message(monkeypatch) -> None:
    scheduled = []

    def fake_enqueue(session, message_id, chat_hash):
        assert message_id == "wamid.example"
        assert chat_hash
        return True

    def fake_process(body, settings, matcher, notifier, conversation_store):
        scheduled.append(body)

    monkeypatch.setattr(whatsapp_meta_webhook, "_enqueue_meta_message", fake_enqueue)
    monkeypatch.setattr(whatsapp_meta_webhook, "_process_meta_message_background", fake_process)

    app = _app_with_meta_settings(Settings(meta_app_secret="app-secret"))
    client = TestClient(app)
    raw_body = json.dumps(_meta_text_payload()).encode("utf-8")

    response = client.post(
        "/whatsapp-meta-webhook",
        content=raw_body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": _meta_signature(raw_body, "app-secret"),
        },
    )

    assert response.status_code == 200
    assert response.text == "ok"
    assert scheduled == [json.loads(raw_body)]


def test_meta_webhook_post_acknowledges_duplicate_without_scheduling(monkeypatch) -> None:
    def fake_enqueue(session, message_id, chat_hash):
        assert message_id == "wamid.duplicate"
        assert chat_hash
        return False

    def fake_process(body, settings, matcher, notifier, conversation_store):
        raise AssertionError("duplicate messages should not be scheduled")

    monkeypatch.setattr(whatsapp_meta_webhook, "_enqueue_meta_message", fake_enqueue)
    monkeypatch.setattr(whatsapp_meta_webhook, "_process_meta_message_background", fake_process)

    app = _app_with_meta_settings(Settings(meta_app_secret="app-secret"))
    client = TestClient(app)
    raw_body = json.dumps(_meta_text_payload("wamid.duplicate")).encode("utf-8")

    response = client.post(
        "/whatsapp-meta-webhook",
        content=raw_body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": _meta_signature(raw_body, "app-secret"),
        },
    )

    assert response.status_code == 200
    assert response.text == "ok"


def test_meta_sender_splits_long_text_before_sending_buttons(monkeypatch) -> None:
    sent_payloads = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, url, headers, json):
            sent_payloads.append(json)
            return FakeResponse()

    monkeypatch.setattr(whatsapp_meta_webhook.httpx, "Client", FakeClient)

    _send_meta_message(
        "15551234567",
        "Resultado\n" + ("Example Person found\n" * 80),
        Settings(meta_access_token="token", meta_phone_number_id="phone-id"),
        buttons=[Button(id="menu", title="Menu")],
    )

    assert len(sent_payloads) == 2
    assert "type" not in sent_payloads[0]
    assert "Example Person found" in sent_payloads[0]["text"]["body"]
    assert sent_payloads[1]["type"] == "interactive"
    assert sent_payloads[1]["interactive"]["body"]["text"] == "Elige una opcion:"
    assert sent_payloads[1]["interactive"]["action"]["buttons"][0]["reply"] == {
        "id": "menu",
        "title": "Menu",
    }


def test_meta_sender_shortens_button_titles_for_cloud_api(monkeypatch) -> None:
    sent_payloads = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, url, headers, json):
            sent_payloads.append(json)
            return FakeResponse()

    monkeypatch.setattr(whatsapp_meta_webhook.httpx, "Client", FakeClient)

    _send_meta_message(
        "15551234567",
        "Elige una de las opciones:",
        Settings(meta_access_token="token", meta_phone_number_id="phone-id"),
        buttons=[
            Button(id="1", title="Buscar por cédula o nombre"),
            Button(id="2", title="Buscar por foto"),
        ],
    )

    replies = [button["reply"] for button in sent_payloads[0]["interactive"]["action"]["buttons"]]
    assert replies == [
        {"id": "1", "title": "Cedula o nombre"},
        {"id": "2", "title": "Buscar por foto"},
    ]
    assert all(len(reply["title"]) <= 20 for reply in replies)


def test_meta_interactive_payload_enforces_button_contract() -> None:
    overlong_id = "x" * (META_BUTTON_ID_LIMIT + 10)
    payload = _meta_interactive_payload(
        "15551234567",
        "Elige una opcion:",
        [
            Button(id="1", title="Buscar por cédula o nombre"),
            Button(id="", title=""),
            Button(id=overlong_id, title="Menu principal"),
            Button(id="extra", title="Extra option should not be sent"),
        ],
    )

    buttons = payload["interactive"]["action"]["buttons"]
    replies = [button["reply"] for button in buttons]

    assert len(replies) == 3
    assert replies[0] == {"id": "1", "title": "Cedula o nombre"}
    assert replies[1] == {"id": "option-2", "title": "Opcion"}
    assert replies[2]["id"] == "x" * META_BUTTON_ID_LIMIT
    assert replies[2]["title"] == "Menu principal"
    assert all(reply["title"] for reply in replies)
    assert all(len(reply["title"]) <= META_BUTTON_TITLE_LIMIT for reply in replies)
    assert all(reply["id"] for reply in replies)
    assert all(len(reply["id"]) <= META_BUTTON_ID_LIMIT for reply in replies)
