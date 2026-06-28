import logging
import random
import secrets
import threading
import time
from copy import deepcopy
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.messaging.types import Button, GenericInboundMessage, MessageKind, MessageSource

log = logging.getLogger(__name__)
_send_lock = threading.Lock()


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


def _selected_reply_text(message: dict[str, Any]) -> str:
    buttons_response = message.get("buttonsResponseMessage") or {}
    if buttons_response:
        return str(
            buttons_response.get("selectedButtonId")
            or buttons_response.get("selectedDisplayText")
            or ""
        ).strip()

    template_reply = message.get("templateButtonReplyMessage") or {}
    if template_reply:
        return str(template_reply.get("selectedId") or "").strip()

    list_response = message.get("listResponseMessage") or {}
    if list_response:
        single_select = list_response.get("singleSelectReply") or {}
        return str(
            single_select.get("selectedRowId")
            or list_response.get("title")
            or ""
        ).strip()

    return ""


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
    elif "extendedTextMessage" in message:
        extended = message.get("extendedTextMessage") or {}
        text = str(extended.get("text") or "").strip()
        kind = MessageKind.TEXT
    elif reply_text := _selected_reply_text(message):
        text = reply_text
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


class EvolutionApiSender(Protocol):
    def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        buttons: list[Button] | None = None,
    ) -> bool:
        raise NotImplementedError

    def send_media_url(
        self,
        chat_id: str,
        media_url: str,
        *,
        mediatype: str = "image",
        mimetype: str = "image/png",
        caption: str | None = None,
        file_name: str = "image.png",
    ) -> bool:
        raise NotImplementedError


class NullEvolutionApiSender:
    def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        buttons: list[Button] | None = None,
    ) -> bool:
        log.info("Evolution API sender disabled; would send to %s: %s", chat_id, text)
        return False

    def send_media_url(
        self,
        chat_id: str,
        media_url: str,
        *,
        mediatype: str = "image",
        mimetype: str = "image/png",
        caption: str | None = None,
        file_name: str = "image.png",
    ) -> bool:
        log.info("Evolution API sender disabled; would send media to %s: %s", chat_id, media_url)
        return False


class EvolutionApiHttpSender:
    def __init__(
        self,
        *,
        base_url: str,
        instance_name: str,
        apikey: str,
        timeout: float,
        delay_min_seconds: float,
        delay_max_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.instance_name = instance_name
        self.apikey = apikey
        self.timeout = timeout
        self.delay_min_seconds = max(0.0, delay_min_seconds)
        self.delay_max_seconds = max(self.delay_min_seconds, delay_max_seconds)

    @staticmethod
    def _number(chat_id: str) -> str:
        value = chat_id.strip()
        if value.endswith("@g.us"):
            return value
        if "@" in value:
            value = value.split("@", 1)[0]
        digits = "".join(ch for ch in value if ch.isdigit())
        return digits or value

    @staticmethod
    def _render_text_options(text: str, buttons: list[Button] | None) -> str:
        if not buttons:
            return text

        lines = [text.rstrip(), "", "Opciones:"]
        for button in buttons:
            lines.append(f"{button.id}. {button.title}")
        return "\n".join(lines)

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "apikey": self.apikey,
        }

    def _post_json(self, path: str, payload: dict[str, Any]) -> bool:
        delay = random.uniform(self.delay_min_seconds, self.delay_max_seconds)
        with _send_lock:
            time.sleep(delay)
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        f"{self.base_url}{path}",
                        headers=self._headers(),
                        json=payload,
                    )
                    response.raise_for_status()
                    return True
            except Exception:
                log.exception("Failed to send Evolution API message to %s", payload.get("number"))
                return False

    def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        buttons: list[Button] | None = None,
    ) -> bool:
        payload = {
            "number": self._number(chat_id),
            "text": self._render_text_options(text, buttons),
            "linkPreview": False,
        }
        return self._post_json(f"/message/sendText/{self.instance_name}", payload)

    def send_media_url(
        self,
        chat_id: str,
        media_url: str,
        *,
        mediatype: str = "image",
        mimetype: str = "image/png",
        caption: str | None = None,
        file_name: str = "image.png",
    ) -> bool:
        payload = {
            "number": self._number(chat_id),
            "mediatype": mediatype,
            "mimetype": mimetype,
            "caption": caption or "",
            "media": media_url,
            "fileName": file_name,
        }
        return self._post_json(f"/message/sendMedia/{self.instance_name}", payload)


def get_evolution_api_sender(settings: Settings) -> EvolutionApiSender:
    if not settings.evolution_api_send_enabled:
        return NullEvolutionApiSender()

    if (
        not settings.evolution_api_base_url
        or not settings.evolution_api_instance_name
        or not settings.evolution_api_apikey
    ):
        log.warning("Evolution API sender credentials missing; outbound messages disabled")
        return NullEvolutionApiSender()

    return EvolutionApiHttpSender(
        base_url=settings.evolution_api_base_url,
        instance_name=settings.evolution_api_instance_name,
        apikey=settings.evolution_api_apikey,
        timeout=settings.evolution_api_send_timeout_seconds,
        delay_min_seconds=settings.evolution_api_send_delay_min_seconds,
        delay_max_seconds=settings.evolution_api_send_delay_max_seconds,
    )
