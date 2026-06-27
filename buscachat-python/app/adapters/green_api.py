import logging
from typing import Protocol, runtime_checkable

import httpx

from app.config import Settings

log = logging.getLogger(__name__)


@runtime_checkable
class Notifier(Protocol):
    """Sends a text message to a chat on the origin channel."""

    def send_text(self, chat_id: str, message: str) -> None:
        raise NotImplementedError


class NullNotifier:
    """No-op notifier for tests and local dev without credentials."""

    def send_text(self, chat_id: str, message: str) -> None:
        log.info("NullNotifier: would send to %s: %s", chat_id, message)


class GreenApiNotifier:
    """Sends WhatsApp messages through the Green API.

    Endpoint: ``POST {base_url}/waInstance{instance_id}/sendMessage/{token}``
    with body ``{"chatId": ..., "message": ...}``.
    """

    def __init__(
        self,
        *,
        base_url: str,
        instance_id: str,
        token: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.instance_id = instance_id
        self.token = token
        self.timeout = timeout

    @staticmethod
    def _to_chat_id(chat_id: str) -> str:
        """Normalize a raw chat id / phone number to Green API's ``chatId``."""
        if "@" in chat_id:
            return chat_id
        digits = "".join(ch for ch in chat_id if ch.isdigit())
        return f"{digits}@c.us"

    def send_text(self, chat_id: str, message: str) -> None:
        url = (
            f"{self.base_url}/waInstance{self.instance_id}"
            f"/sendMessage/{self.token}"
        )
        payload = {"chatId": self._to_chat_id(chat_id), "message": message}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()


def get_notifier(settings: Settings) -> Notifier:
    """Return the configured notifier.

    Falls back to :class:`NullNotifier` when Green API is selected but no
    credentials are configured, so local dev never crashes on a missing token.
    """
    if settings.notifier == "null":
        return NullNotifier()

    if not settings.green_api_instance_id or not settings.green_api_token:
        log.warning("Green API credentials missing; using NullNotifier")
        return NullNotifier()

    return GreenApiNotifier(
        base_url=settings.green_api_base_url,
        instance_id=settings.green_api_instance_id,
        token=settings.green_api_token,
    )
