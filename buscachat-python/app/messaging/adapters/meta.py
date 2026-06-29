from typing import Any

from app.messaging.types import GenericInboundMessage, MessageKind, MessageSource


def adapt_meta_message(body: dict[str, Any]) -> GenericInboundMessage | None:
    try:
        entry = (body.get("entry") or [{}])[0]
        change = (entry.get("changes") or [{}])[0]
        value = change.get("value") or {}
        messages = value.get("messages") or []
        contacts = value.get("contacts") or [{}]
        if not messages:
            return None
        msg = messages[0]
        contact = contacts[0]
    except (IndexError, KeyError, TypeError):
        return None

    msg_type = msg.get("type", "text")
    text = ""
    image_ref = None
    kind = MessageKind.TEXT

    if msg_type == "text":
        text = (msg.get("text") or {}).get("body", "")
    elif msg_type == "image":
        text = (msg.get("image") or {}).get("caption", "")
        image_ref = (msg.get("image") or {}).get("id")
        kind = MessageKind.IMAGE
    elif msg_type == "interactive":
        interactive_data = msg.get("interactive") or {}
        button_reply = interactive_data.get("button_reply") or {}
        text = button_reply.get("id", "")
    elif msg_type == "audio":
        text = "[audio]"
    elif msg_type == "document":
        text = "[documento]"

    wa_id = msg.get("from", "")
    if not wa_id:
        return None

    return GenericInboundMessage(
        source=MessageSource.META,
        sender_id=wa_id,
        chat_id=wa_id,
        kind=kind,
        text=text.strip(),
        image_ref=image_ref,
        message_id=msg.get("id"),
        sender_name=(contact.get("profile") or {}).get("name", ""),
        raw=body,
    )
