from typing import Any

from app.messaging.types import GenericInboundMessage, MessageKind, MessageSource


def adapt_green_api_message(body: dict[str, Any]) -> GenericInboundMessage:
    md = body.get("messageData") or {}
    sd = body.get("senderData") or {}

    is_image = md.get("typeMessage") == "imageMessage"
    text = ""
    image_ref = None

    if is_image:
        text = md.get("caption") or ""
        if md.get("fileMessageData"):
            image_ref = md["fileMessageData"].get("downloadUrl")
    elif md.get("textMessageData"):
        text = md["textMessageData"].get("textMessage", "")

    raw_sender = sd.get("sender", "")
    chat_id = raw_sender if "@" in raw_sender else f"{raw_sender}@c.us"

    return GenericInboundMessage(
        source=MessageSource.GREEN_API,
        sender_id=raw_sender,
        chat_id=chat_id,
        kind=MessageKind.IMAGE if is_image else MessageKind.TEXT,
        text=text.strip(),
        image_ref=image_ref,
        sender_name=sd.get("senderName") or "",
        raw=body,
    )
