import threading
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.messaging.types import Button, GenericInboundMessage, GenericOutboundMessage


class WebChatMessage(BaseModel):
    id: int
    role: Literal["user", "bot"]
    text: str
    image_ref: str | None = None
    action: str | None = None
    buttons: list[Button] = Field(default_factory=list)
    created_at: datetime


class InMemoryWebChatStore:
    """Shared in-process transcript for the browser test channel."""

    def __init__(self) -> None:
        self._messages: list[WebChatMessage] = []
        self._next_id = 1
        self._lock = threading.Lock()

    def add_user_message(self, message: GenericInboundMessage) -> WebChatMessage:
        text = message.text or ("[image]" if message.image_ref else "")
        return self._append(
            role="user",
            text=text,
            image_ref=message.image_ref,
        )

    def add_bot_message(self, message: GenericOutboundMessage) -> WebChatMessage:
        return self._append(
            role="bot",
            text=message.text,
            action=message.action,
            buttons=message.buttons,
        )

    def list_messages(self, after_id: int = 0) -> list[WebChatMessage]:
        with self._lock:
            return [message for message in self._messages if message.id > after_id]

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
            self._next_id = 1

    def _append(
        self,
        *,
        role: Literal["user", "bot"],
        text: str,
        image_ref: str | None = None,
        action: str | None = None,
        buttons: list[Button] | None = None,
    ) -> WebChatMessage:
        with self._lock:
            message = WebChatMessage(
                id=self._next_id,
                role=role,
                text=text,
                image_ref=image_ref,
                action=action,
                buttons=list(buttons or []),
                created_at=datetime.now(UTC),
            )
            self._next_id += 1
            self._messages.append(message)
            return message


web_chat_store = InMemoryWebChatStore()
