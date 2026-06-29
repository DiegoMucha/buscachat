from typing import Any

from app.messaging.types import GenericInboundMessage, MessageKind, MessageSource

WEB_CHAT_ID = "web-test-chat"
WEB_SENDER_ID = "web-test-user"


def adapt_web_message(payload: dict[str, Any]) -> GenericInboundMessage:
    text = str(payload.get("text") or "").strip()
    image_ref = str(payload.get("image_ref") or "").strip() or None

    return GenericInboundMessage(
        source=MessageSource.WEB,
        sender_id=WEB_SENDER_ID,
        chat_id=WEB_CHAT_ID,
        kind=MessageKind.IMAGE if image_ref else MessageKind.TEXT,
        text=text,
        image_ref=image_ref,
        sender_name="Web tester",
        raw=dict(payload),
    )
