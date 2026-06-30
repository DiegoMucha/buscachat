import logging
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)


@runtime_checkable
class Notifier(Protocol):
    """Sends a text message to a chat on the origin channel."""

    def send_text(self, chat_id: str, message: str) -> None:
        raise NotImplementedError


class NullNotifier:
    """No-op notifier for tests and local development."""

    def send_text(self, chat_id: str, message: str) -> None:
        log.info("NullNotifier: would send to %s: %s", chat_id, message)


def get_notifier() -> Notifier:
    return NullNotifier()
