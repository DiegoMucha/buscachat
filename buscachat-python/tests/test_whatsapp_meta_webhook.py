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
from app.routers.whatsapp_meta_webhook import _send_meta_message, _verify_meta_signature, router


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
        "59170000000",
        "Resultado\n" + ("Juan Perez encontrado\n" * 80),
        Settings(meta_access_token="token", meta_phone_number_id="phone-id"),
        buttons=[Button(id="menu", title="Menu")],
    )

    assert len(sent_payloads) == 2
    assert "type" not in sent_payloads[0]
    assert "Juan Perez encontrado" in sent_payloads[0]["text"]["body"]
    assert sent_payloads[1]["type"] == "interactive"
    assert sent_payloads[1]["interactive"]["body"]["text"] == "Elige una opcion:"
    assert sent_payloads[1]["interactive"]["action"]["buttons"][0]["reply"] == {
        "id": "menu",
        "title": "Menu",
    }
