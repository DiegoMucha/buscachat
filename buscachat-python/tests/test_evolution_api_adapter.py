import pytest

from app.config import Settings
from app.messaging.adapters.evolution_api import (
    EvolutionApiAuthenticationError,
    EvolutionApiHttpSender,
    adapt_evolution_api_message,
    redact_evolution_api_secret,
    require_evolution_api_key,
)
from app.messaging.types import Button, MessageKind, MessageSource


def _base_payload(message: dict, message_type: str = "conversation") -> dict:
    return {
        "data": {
            "key": {
                "id": "3EB0EACEF7FB049A21BAC7",
                "fromMe": False,
                "remoteJid": "15551234567@s.whatsapp.net",
                "remoteJidAlt": "15551234567@s.whatsapp.net",
            },
            "message": message,
            "pushName": "Example Sender",
            "messageType": message_type,
        },
        "event": "messages.upsert",
        "apikey": "secret",
    }


def test_require_evolution_api_key_accepts_matching_body_key() -> None:
    payload = _base_payload({"conversation": "hola"})

    require_evolution_api_key(
        payload,
        Settings(evolution_api_webhook_apikey="secret"),
    )


def test_require_evolution_api_key_rejects_wrong_key() -> None:
    payload = _base_payload({"conversation": "hola"})

    with pytest.raises(EvolutionApiAuthenticationError):
        require_evolution_api_key(
            payload,
            Settings(evolution_api_webhook_apikey="different"),
        )


def test_adapt_evolution_api_text_message_uses_remote_jid_as_sender() -> None:
    message = adapt_evolution_api_message(
        _base_payload({"conversation": "hola bienvenido"})
    )

    assert message is not None
    assert message.source == MessageSource.EVOLUTION_API
    assert message.kind == MessageKind.TEXT
    assert message.sender_id == "15551234567@s.whatsapp.net"
    assert message.chat_id == "15551234567@s.whatsapp.net"
    assert message.text == "hola bienvenido"
    assert message.sender_name == "Example Sender"


def test_adapt_evolution_api_image_message_uses_media_url_and_caption() -> None:
    payload = _base_payload(
        {
            "mediaUrl": "https://example.test/image.jpg",
            "imageMessage": {"caption": "hola doggo"},
        },
        message_type="imageMessage",
    )

    message = adapt_evolution_api_message(payload)

    assert message is not None
    assert message.kind == MessageKind.IMAGE
    assert message.image_ref == "https://example.test/image.jpg"
    assert message.text == "hola doggo"


def test_redact_evolution_api_secret_supports_captured_wrapper_shape() -> None:
    payload = {"body": _base_payload({"conversation": "hola"})}

    redacted = redact_evolution_api_secret(payload)

    assert redacted["body"]["apikey"] == "***redacted***"
    assert payload["body"]["apikey"] == "secret"


def test_sender_resolves_instance_id_to_name_after_404(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, data: object | None = None) -> None:
            self.status_code = status_code
            self._data = data

        def json(self) -> object:
            return self._data

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise AssertionError(f"unexpected HTTP error in test: {self.status_code}")

    class FakeClient:
        posts: list[dict] = []
        gets: list[str] = []

        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict) -> FakeResponse:
            self.posts.append({"url": url, "headers": headers, "json": json})
            if url.endswith("/message/sendText/instance-id"):
                return FakeResponse(404)
            return FakeResponse(201)

        def get(self, url: str, *, headers: dict[str, str]) -> FakeResponse:
            self.gets.append(url)
            return FakeResponse(200, [{"id": "instance-id", "name": "LozaBot II"}])

    FakeClient.posts = []
    FakeClient.gets = []
    monkeypatch.setattr("app.messaging.adapters.evolution_api.httpx.Client", FakeClient)

    sender = EvolutionApiHttpSender(
        base_url="https://evolution-api.example.test",
        instance_name="instance-id",
        apikey="secret",
        timeout=30,
        delay_min_seconds=0,
        delay_max_seconds=0,
    )

    sent = sender.send_text(
        "15551234567@s.whatsapp.net",
        "hola",
        buttons=[Button(id="1", title="Buscar")],
    )

    assert sent is True
    assert FakeClient.gets == ["https://evolution-api.example.test/instance/fetchInstances"]
    assert [post["url"] for post in FakeClient.posts] == [
        "https://evolution-api.example.test/message/sendText/instance-id",
        "https://evolution-api.example.test/message/sendText/LozaBot%20II",
    ]
    assert FakeClient.posts[-1]["json"] == {
        "number": "15551234567",
        "text": "hola\n\nOpciones:\n1. Buscar",
        "linkPreview": False,
    }
