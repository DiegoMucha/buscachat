import secrets
from copy import deepcopy
from typing import Any

from app.config import Settings
from app.messaging.types import GenericInboundMessage, MessageKind, MessageSource


class EvolutionApiAuthenticationError(ValueError):
    pass


def _payload_body(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("body")
    if isinstance(body, dict) and "data" in body:
        return body
    return payload


def redact_evolution_api_secret(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    redacted = deepcopy(payload)
    body = _payload_body(redacted)
    if isinstance(body, dict) and "apikey" in body:
        body["apikey"] = "***redacted***"
    return redacted


def require_evolution_api_key(payload: dict[str, Any], settings: Settings) -> None:
    expected = settings.evolution_api_webhook_apikey
    body = _payload_body(payload)
    provided = body.get("apikey") if isinstance(body, dict) else None

    if not expected:
        raise EvolutionApiAuthenticationError("Evolution API webhook key is not configured")
    if not isinstance(provided, str) or not secrets.compare_digest(provided, expected):
        raise EvolutionApiAuthenticationError("Invalid Evolution API webhook key")


def adapt_evolution_api_message(payload: dict[str, Any]) -> GenericInboundMessage | None:
    body = _payload_body(payload)
    data = body.get("data") or {}
    key = data.get("key") or {}

    if key.get("fromMe"):
        return None

    message = data.get("message") or {}
    message_type = data.get("messageType") or ""

    remote_jid = key.get("remoteJid") or key.get("remoteJidAlt") or ""
    sender_id = str(remote_jid)
    chat_id = sender_id
    text = ""
    image_ref = None
    kind = MessageKind.UNKNOWN

    if "conversation" in message:
        text = str(message.get("conversation") or "").strip()
        kind = MessageKind.TEXT
    elif message_type == "imageMessage" or "imageMessage" in message:
        image = message.get("imageMessage") or {}
        text = str(image.get("caption") or "").strip()
        image_ref = message.get("mediaUrl") or image.get("url")
        kind = MessageKind.IMAGE
    elif message_type:
        text = str(message.get("text") or "").strip()

    if not chat_id:
        return None

    return GenericInboundMessage(
        source=MessageSource.EVOLUTION_API,
        sender_id=sender_id,
        chat_id=chat_id,
        kind=kind,
        text=text,
        image_ref=image_ref,
        message_id=key.get("id"),
        sender_name=data.get("pushName"),
        raw=body,
    )
