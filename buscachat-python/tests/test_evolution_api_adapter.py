import pytest

from app.config import Settings
from app.messaging.adapters.evolution_api import (
    EvolutionApiAuthenticationError,
    adapt_evolution_api_message,
    redact_evolution_api_secret,
    require_evolution_api_key,
)
from app.messaging.types import MessageKind, MessageSource


def _base_payload(message: dict, message_type: str = "conversation") -> dict:
    return {
        "data": {
            "key": {
                "id": "3EB0EACEF7FB049A21BAC7",
                "fromMe": False,
                "remoteJid": "59175034784@s.whatsapp.net",
                "remoteJidAlt": "59175034784@s.whatsapp.net",
            },
            "message": message,
            "pushName": "Sergio Loza",
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
    assert message.sender_id == "59175034784@s.whatsapp.net"
    assert message.chat_id == "59175034784@s.whatsapp.net"
    assert message.text == "hola bienvenido"
    assert message.sender_name == "Sergio Loza"


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
