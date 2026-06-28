import logging
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlmodel import Session

from app.adapters.green_api import Notifier
from app.config import Settings, get_settings
from app.database import get_session
from app.face import FaceMatcher
from app.messaging.adapters.meta import adapt_meta_message
from app.messaging.conversation import save_embedding_for_chat
from app.messaging.dependencies import (
    get_face_matcher_dependency,
    get_notifier_dependency,
)
from app.messaging.pipeline import run_message_pipeline
from app.messaging.types import Button, MessageKind

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/whatsapp-meta-webhook",
    tags=["whatsapp-meta-webhook"],
)


def _download_meta_image(
    media_id: str,
    access_token: str,
    *,
    timeout: float = 30.0,
) -> bytes | None:
    try:
        with httpx.Client(timeout=timeout) as client:
            url_response = client.get(
                f"https://graph.facebook.com/v19.0/{media_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            url_response.raise_for_status()
            download_url = url_response.json().get("url")
            if not download_url:
                return None

            image_response = client.get(
                download_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            image_response.raise_for_status()
            return image_response.content
    except Exception:
        log.exception("Failed to download Meta image %s", media_id)
        return None


def _send_meta_message(
    chat_id: str,
    text: str,
    settings: Settings,
    buttons: list[Button] | None = None,
) -> None:
    if not settings.meta_access_token or not settings.meta_phone_number_id:
        log.warning("Meta credentials missing; not sending to %s", chat_id)
        return

    if buttons:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": chat_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": button.id, "title": button.title}}
                        for button in buttons[:3]
                    ]
                },
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": chat_id,
            "text": {"body": text},
        }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                f"https://graph.facebook.com/v19.0/{settings.meta_phone_number_id}/messages",
                headers={
                    "Authorization": f"Bearer {settings.meta_access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
    except Exception:
        log.exception("Failed to send Meta message to %s", chat_id)


@router.api_route("", methods=["GET", "POST"])
async def whatsapp_meta_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dependency)],
    notifier: Annotated[Notifier, Depends(get_notifier_dependency)],
    settings: Annotated[Settings, Depends(get_settings)],
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    if request.method == "GET":
        if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
            return Response(content=str(hub_challenge or ""), media_type="text/plain")
        return Response(content="Verification failed", status_code=403)

    body = await request.json()
    message = adapt_meta_message(body)
    if message is None:
        return Response(content="ok", media_type="text/plain")

    if message.kind == MessageKind.IMAGE and message.image_ref and settings.meta_access_token:
        image_bytes = _download_meta_image(
            message.image_ref,
            settings.meta_access_token,
            timeout=settings.image_download_timeout_seconds,
        )
        if image_bytes is None:
            _send_meta_message(
                message.chat_id,
                "No se pudo descargar la imagen. Intenta de nuevo.",
                settings,
            )
            return Response(content="ok", media_type="text/plain")
        message.image_embedding = matcher.embed(image_bytes)
        save_embedding_for_chat(message.chat_id, message.image_embedding)

    outbound = run_message_pipeline(
        message,
        session=session,
        matcher=matcher,
        notifier=notifier,
        settings=settings,
    )
    _send_meta_message(outbound.chat_id, outbound.text, settings, buttons=outbound.buttons)
    return Response(content="ok", media_type="text/plain")
