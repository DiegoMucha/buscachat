import hashlib
import hmac
import json
import logging
import time
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
    get_conversation_state_store_dependency,
    get_face_matcher_dependency,
    get_notifier_dependency,
)
from app.messaging.pipeline import run_message_pipeline
from app.messaging.session_store import ConversationStateStore
from app.messaging.types import Button, MessageKind

log = logging.getLogger(__name__)

META_TEXT_BODY_LIMIT = 4096
META_INTERACTIVE_BODY_LIMIT = 1024
META_BUTTON_PROMPT = "Elige una opcion:"

router = APIRouter(
    prefix="/whatsapp-meta-webhook",
    tags=["whatsapp-meta-webhook"],
)


def _text_prefix(text: str | None, length: int = 3) -> str:
    return (text or "")[:length].replace("\n", "\\n").replace("\r", "\\r")


def _identifier_hash(value: str | None, secret: str = "", length: int = 12) -> str:
    clean_value = value or ""
    if secret:
        digest = hmac.new(
            secret.encode("utf-8"), clean_value.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    else:
        digest = hashlib.sha256(clean_value.encode("utf-8")).hexdigest()
    return digest[:length]


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _state_step(
    conversation_store: ConversationStateStore, chat_id: str, secret: str = ""
) -> str:
    try:
        return str(conversation_store.get_state(chat_id).get("paso", "unknown"))
    except Exception:
        log.exception(
            "Failed to read conversation state for Meta chat_hash=%s",
            _identifier_hash(chat_id, secret),
        )
        return "unknown"


def _payload_text(payload: dict[str, Any]) -> str:
    if payload.get("type") == "interactive":
        return str(
            ((payload.get("interactive") or {}).get("body") or {}).get("text") or ""
        )
    return str((payload.get("text") or {}).get("body") or "")


def _verify_meta_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected_signature = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature_header, f"sha256={expected_signature}")


def _download_meta_image(
    media_id: str,
    graph_api_version: str,
    access_token: str,
    *,
    timeout: float = 30.0,
) -> bytes | None:
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            url_response = client.get(
                f"https://graph.facebook.com/{graph_api_version}/{media_id}",
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
            log.info(
                "Meta image download succeeded media_id=%s bytes=%s elapsed_ms=%.1f",
                media_id,
                len(image_response.content),
                _elapsed_ms(start),
            )
            return image_response.content
    except Exception:
        log.exception(
            "Failed to download Meta image %s elapsed_ms=%.1f",
            media_id,
            _elapsed_ms(start),
        )
        return None


def _send_meta_message(
    chat_id: str,
    text: str,
    settings: Settings,
    buttons: list[Button] | None = None,
) -> None:
    chat_hash = _identifier_hash(chat_id, settings.meta_app_secret)
    if not settings.meta_access_token or not settings.meta_phone_number_id:
        log.warning(
            "Meta credentials missing; not sending chat_hash=%s text_prefix=%r text_len=%s buttons=%s",
            chat_hash,
            _text_prefix(text),
            len(text),
            len(buttons or []),
        )
        return

    send_start = time.perf_counter()
    payloads: list[dict[str, Any]]
    if buttons:
        if len(text) > META_INTERACTIVE_BODY_LIMIT:
            payloads = [
                _meta_text_payload(chat_id, chunk) for chunk in _split_meta_text(text)
            ]
            payloads.append(
                _meta_interactive_payload(chat_id, META_BUTTON_PROMPT, buttons)
            )
        else:
            payloads = [_meta_interactive_payload(chat_id, text, buttons)]
    else:
        payloads = [
            _meta_text_payload(chat_id, chunk) for chunk in _split_meta_text(text)
        ]

    log.info(
        "Meta outbound send start chat_hash=%s payloads=%s buttons=%s text_prefix=%r text_len=%s",
        chat_hash,
        len(payloads),
        len(buttons or []),
        _text_prefix(text),
        len(text),
    )

    try:
        with httpx.Client(timeout=15.0) as client:
            for index, payload in enumerate(payloads, start=1):
                payload_start = time.perf_counter()
                payload_type = str(payload.get("type") or "text")
                payload_text = _payload_text(payload)
                log.info(
                    "Meta outbound payload start chat_hash=%s payload=%s/%s type=%s text_prefix=%r text_len=%s",
                    chat_hash,
                    index,
                    len(payloads),
                    payload_type,
                    _text_prefix(payload_text),
                    len(payload_text),
                )
                response = client.post(
                    f"https://graph.facebook.com/{settings.meta_graph_api_version}/{settings.meta_phone_number_id}/messages",
                    headers={
                        "Authorization": f"Bearer {settings.meta_access_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                log.info(
                    "Meta outbound payload sent chat_hash=%s payload=%s/%s type=%s status=%s elapsed_ms=%.1f",
                    chat_hash,
                    index,
                    len(payloads),
                    payload_type,
                    getattr(response, "status_code", "unknown"),
                    _elapsed_ms(payload_start),
                )
        log.info(
            "Meta outbound send done chat_hash=%s elapsed_ms=%.1f",
            chat_hash,
            _elapsed_ms(send_start),
        )
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.exception(
            "Failed to send Meta message chat_hash=%s status=%s body=%s elapsed_ms=%.1f",
            chat_hash,
            response.status_code,
            response.text[:500],
            _elapsed_ms(send_start),
        )
    except Exception:
        log.exception(
            "Failed to send Meta message chat_hash=%s elapsed_ms=%.1f",
            chat_hash,
            _elapsed_ms(send_start),
        )


def _meta_text_payload(chat_id: str, text: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": chat_id,
        "text": {"body": text},
    }


def _meta_interactive_payload(
    chat_id: str, text: str, buttons: list[Button]
) -> dict[str, Any]:
    return {
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


def _split_meta_text(text: str, limit: int = META_TEXT_BODY_LIMIT) -> list[str]:
    clean_text = text.strip()
    if not clean_text:
        return [""]
    if len(clean_text) <= limit:
        return [clean_text]

    chunks: list[str] = []
    remaining = clean_text
    while len(remaining) > limit:
        split_at = max(
            remaining.rfind("\n\n", 0, limit + 1),
            remaining.rfind("\n", 0, limit + 1),
            remaining.rfind(" ", 0, limit + 1),
        )
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


@router.get("")
async def verify_whatsapp_meta_webhook(
    settings: Annotated[Settings, Depends(get_settings)],
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        return Response(content=str(hub_challenge or ""), media_type="text/plain")
    return Response(content="Verification failed", status_code=403)


@router.post("")
async def whatsapp_meta_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dependency)],
    notifier: Annotated[Notifier, Depends(get_notifier_dependency)],
    conversation_store: Annotated[
        ConversationStateStore,
        Depends(get_conversation_state_store_dependency),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    request_start = time.perf_counter()
    raw_body = await request.body()
    signature_header = request.headers.get("x-hub-signature-256")
    if not _verify_meta_signature(
        raw_body,
        signature_header,
        settings.meta_app_secret,
    ):
        log.warning(
            "Rejected Meta webhook POST with invalid signature elapsed_ms=%.1f",
            _elapsed_ms(request_start),
        )
        return Response(content="Invalid signature", status_code=403)

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        log.warning(
            "Rejected Meta webhook POST with invalid JSON bytes=%s elapsed_ms=%.1f",
            len(raw_body),
            _elapsed_ms(request_start),
        )
        return Response(content="Invalid JSON", status_code=400)

    message = adapt_meta_message(body)
    if message is None:
        log.info(
            "Meta webhook received no message bytes=%s elapsed_ms=%.1f",
            len(raw_body),
            _elapsed_ms(request_start),
        )
        return Response(content="ok", media_type="text/plain")

    chat_hash = _identifier_hash(message.chat_id, settings.meta_app_secret)
    step_before = _state_step(
        conversation_store, message.chat_id, settings.meta_app_secret
    )
    log.info(
        "Meta inbound message received chat_hash=%s message_id=%s kind=%s step=%s "
        "text_prefix=%r text_len=%s has_image=%s",
        chat_hash,
        message.message_id,
        message.kind,
        step_before,
        _text_prefix(message.text),
        len(message.text),
        bool(message.image_ref),
    )

    if (
        message.kind == MessageKind.IMAGE
        and message.image_ref
        and settings.meta_access_token
    ):
        image_start = time.perf_counter()
        image_bytes = _download_meta_image(
            message.image_ref,
            settings.meta_graph_api_version,
            settings.meta_access_token,
            timeout=settings.image_download_timeout_seconds,
        )
        if image_bytes is None:
            _send_meta_message(
                message.chat_id,
                "No se pudo descargar la imagen. Intenta de nuevo.",
                settings,
            )
            log.info(
                "Meta webhook completed after image download failure chat_hash=%s elapsed_ms=%.1f",
                chat_hash,
                _elapsed_ms(request_start),
            )
            return Response(content="ok", media_type="text/plain")
        message.image_bytes = image_bytes
        message.image_embedding = matcher.embed(image_bytes)
        save_embedding_for_chat(
            message.chat_id,
            message.image_embedding,
            conversation_store,
        )
        log.info(
            "Meta image processed chat_hash=%s embedding=%s elapsed_ms=%.1f",
            chat_hash,
            bool(message.image_embedding),
            _elapsed_ms(image_start),
        )

    pipeline_start = time.perf_counter()
    outbound = run_message_pipeline(
        message,
        session=session,
        matcher=matcher,
        notifier=notifier,
        settings=settings,
        conversation_store=conversation_store,
    )
    step_after = _state_step(
        conversation_store, message.chat_id, settings.meta_app_secret
    )
    log.info(
        "Meta conversation pipeline done chat_hash=%s step_before=%s step_after=%s action=%s "
        "output_prefix=%r output_len=%s buttons=%s elapsed_ms=%.1f",
        chat_hash,
        step_before,
        step_after,
        outbound.action,
        _text_prefix(outbound.text),
        len(outbound.text),
        len(outbound.buttons),
        _elapsed_ms(pipeline_start),
    )
    _send_meta_message(
        outbound.chat_id, outbound.text, settings, buttons=outbound.buttons
    )
    log.info(
        "Meta webhook completed chat_hash=%s elapsed_ms=%.1f",
        chat_hash,
        _elapsed_ms(request_start),
    )
    return Response(content="ok", media_type="text/plain")
