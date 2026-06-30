from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MessageSource(StrEnum):
    META = "meta"
    WEB = "web"


class MessageKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    UNKNOWN = "unknown"


class Button(BaseModel):
    id: str
    title: str


class GenericInboundMessage(BaseModel):
    source: MessageSource
    sender_id: str
    chat_id: str
    kind: MessageKind = MessageKind.UNKNOWN
    text: str = ""
    image_ref: str | None = None
    image_embedding: list[float] | None = None
    message_id: str | None = None
    sender_name: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_conversation_payload(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "canal": self.source.value,
            "tipo": "imagen" if self.kind == MessageKind.IMAGE else "texto",
            "text": self.text,
            "imagen_ref": self.image_ref,
            "chat_id": self.chat_id,
            "sender": self.sender_id,
            "nombre": self.sender_name or "",
            "_embedding": self.image_embedding,
        }


class GenericOutboundMessage(BaseModel):
    source: MessageSource
    chat_id: str
    text: str
    action: str | None = None
    buttons: list[Button] = Field(default_factory=list)
