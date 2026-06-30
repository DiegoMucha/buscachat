import hashlib
import hmac
import json
import logging
import time
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session
from starlette.requests import ClientDisconnect

from app.config import Settings, get_settings
from app.database import engine, get_session
from app.face import FaceMatcher
from app.messaging.adapters.meta import adapt_meta_message
from app.messaging.conversation import save_embedding_for_chat
from app.messaging.dependencies import (
    get_conversation_state_store_dependency,
    get_face_matcher_dependency,
    get_notifier_dependency,
)
from app.messaging.notifier import Notifier
from app.messaging.pipeline import run_message_pipeline
from app.messaging.session_store import ConversationStateStore
from app.messaging.types import Button, MessageKind
from app.models import MetaWebhookMessage, utc_now

log = logging.getLogger(__name__)

META_TEXT_BODY_LIMIT = 4096
META_INTERACTIVE_BODY_LIMIT = 1024
META_BUTTON_ID_LIMIT = 256
META_BUTTON_TITLE_LIMIT = 20
META_BUTTON_PROMPT = "Elige una opcion:"
META_BUTTON_TITLE_OVERRIDES = {
    "buscar por cédula o nombre": "Cedula o nombre",
    "buscar por cedula o nombre": "Cedula o nombre",
}

router = APIRouter(
    prefix="/whatsapp-meta-webhook",
    tags=["whatsapp-meta-webhook"],
)


def _text_prefix(text: str | None, length: int = 3) -> str:
    return (text or "")[:length].replace("\n", "\\n").replace("\r", "\\r")


def _identifier_hash(value: str | None, secret: str = "", length: int = 12) -> str:
    clean_value = value or ""
    if secret:
        digest = hmac.new(secret.encode("utf-8"), clean_value.encode("utf-8"), hashlib.sha256).hexdigest()
    else:
        digest = hashlib.sha256(clean_value.encode("utf-8")).hexdigest()
    return digest[:length]


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _state_step(conversation_store: ConversationStateStore, chat_id: str, secret: str = "") -> str:
    try:
        return str(conversation_store.get_state(chat_id).get("paso", "unknown"))
    except Exception:
        log.exception("Failed to read conversation state for Meta chat_hash=%s", _identifier_hash(chat_id, secret))
        return "unknown"


def _payload_text(payload: dict[str, Any]) -> str:
    if payload.get("type") == "interactive":
        return str(((payload.get("interactive") or {}).get("body") or {}).get("text") or "")
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
        log.exception("Failed to download Meta image %s elapsed_ms=%.1f", media_id, _elapsed_ms(start))
        return None


def _send_meta_message(
    chat_id: str,
    text: str,
    settings: Settings,
    buttons: list[Button] | None = None,
) -> bool:
    chat_hash = _identifier_hash(chat_id, settings.meta_app_secret)
    if not settings.meta_access_token or not settings.meta_phone_number_id:
        log.warning(
            "Meta credentials missing; not sending chat_hash=%s text_prefix=%r text_len=%s buttons=%s",
            chat_hash,
            _text_prefix(text),
            len(text),
            len(buttons or []),
        )
        return False

    send_start = time.perf_counter()
    payloads: list[dict[str, Any]]
    if buttons:
        if len(text) > META_INTERACTIVE_BODY_LIMIT:
            payloads = [_meta_text_payload(chat_id, chunk) for chunk in _split_meta_text(text)]
            payloads.append(_meta_interactive_payload(chat_id, META_BUTTON_PROMPT, buttons))
        else:
            payloads = [_meta_interactive_payload(chat_id, text, buttons)]
    else:
        payloads = [_meta_text_payload(chat_id, chunk) for chunk in _split_meta_text(text)]

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
        log.info("Meta outbound send done chat_hash=%s elapsed_ms=%.1f", chat_hash, _elapsed_ms(send_start))
        return True
    except httpx.HTTPStatusError as exc:
        response = exc.response
        log.exception(
            "Failed to send Meta message chat_hash=%s status=%s body=%s elapsed_ms=%.1f",
            chat_hash,
            response.status_code,
            response.text[:500],
            _elapsed_ms(send_start),
        )
        return False
    except Exception:
        log.exception("Failed to send Meta message chat_hash=%s elapsed_ms=%.1f", chat_hash, _elapsed_ms(send_start))
        return False


def _meta_text_payload(chat_id: str, text: str) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": chat_id,
        "text": {"body": text},
    }


def _meta_interactive_payload(chat_id: str, text: str, buttons: list[Button]) -> dict[str, Any]:
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
                    {
                        "type": "reply",
                        "reply": {
                            "id": _meta_button_id(button.id, index),
                            "title": _meta_button_title(button.title),
                        },
                    }
                    for index, button in enumerate(buttons[:3], start=1)
                ]
            },
        },
    }


def _meta_button_id(button_id: str, fallback_index: int) -> str:
    clean_id = " ".join(button_id.split())
    if not clean_id:
        clean_id = f"option-{fallback_index}"
    return clean_id[:META_BUTTON_ID_LIMIT]


def _meta_button_title(title: str) -> str:
    clean_title = " ".join(title.split())
    override = META_BUTTON_TITLE_OVERRIDES.get(clean_title.casefold())
    if override:
        return override
    if len(clean_title) <= META_BUTTON_TITLE_LIMIT:
        return clean_title or "Opcion"
    return clean_title[:META_BUTTON_TITLE_LIMIT].rstrip() or "Opcion"


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


def _enqueue_meta_message(session: Session, message_id: str | None, chat_hash: str) -> bool:
    if not message_id:
        log.warning("Meta inbound message has no message_id; processing without dedupe chat_hash=%s", chat_hash)
        return True

    session.add(MetaWebhookMessage(message_id=message_id, chat_hash=chat_hash))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        log.info("Meta duplicate message ignored message_id=%s chat_hash=%s", message_id, chat_hash)
        return False

    return True


def _set_meta_message_status(
    session: Session,
    message_id: str | None,
    status: str,
    *,
    error: str | None = None,
) -> None:
    if not message_id:
        return

    record = session.get(MetaWebhookMessage, message_id)
    if record is None:
        return

    record.status = status
    record.error = error[:2000] if error else None
    if status == "processing" and record.started_at is None:
        record.started_at = utc_now()
    if status in {"processed", "failed"}:
        record.processed_at = utc_now()
    session.add(record)
    session.commit()


def _process_meta_message_background(
    message_body: dict[str, Any],
    settings: Settings,
    matcher: FaceMatcher,
    notifier: Notifier,
    conversation_store: ConversationStateStore,
) -> None:
    request_start = time.perf_counter()
    message = adapt_meta_message(message_body)
    if message is None:
        log.info("Meta background task skipped because message could not be adapted")
        return

    chat_hash = _identifier_hash(message.chat_id, settings.meta_app_secret)
    with Session(engine) as session:
        try:
            _set_meta_message_status(session, message.message_id, "processing")
            step_before = _state_step(conversation_store, message.chat_id, settings.meta_app_secret)
            log.info(
                "Meta background processing start chat_hash=%s message_id=%s kind=%s step=%s "
                "text_prefix=%r text_len=%s has_image=%s",
                chat_hash,
                message.message_id,
                message.kind,
                step_before,
                _text_prefix(message.text),
                len(message.text),
                bool(message.image_ref),
            )

            if message.kind == MessageKind.IMAGE and message.image_ref and settings.meta_access_token:
                image_start = time.perf_counter()
                image_bytes = _download_meta_image(
                    message.image_ref,
                    settings.meta_graph_api_version,
                    settings.meta_access_token,
                    timeout=settings.image_download_timeout_seconds,
                )
                if image_bytes is None:
                    sent = _send_meta_message(
                        message.chat_id,
                        "No se pudo descargar la imagen. Intenta de nuevo.",
                        settings,
                    )
                    if not sent:
                        raise RuntimeError("Meta outbound send failed after image download failure")
                    _set_meta_message_status(session, message.message_id, "processed")
                    log.info(
                        "Meta background completed after image download failure chat_hash=%s elapsed_ms=%.1f",
                        chat_hash,
                        _elapsed_ms(request_start),
                    )
                    return
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
            step_after = _state_step(conversation_store, message.chat_id, settings.meta_app_secret)
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
            sent = _send_meta_message(outbound.chat_id, outbound.text, settings, buttons=outbound.buttons)
            if not sent:
                raise RuntimeError("Meta outbound send failed")
            _set_meta_message_status(session, message.message_id, "processed")
            log.info(
                "Meta background processing completed chat_hash=%s elapsed_ms=%.1f",
                chat_hash,
                _elapsed_ms(request_start),
            )
        except Exception as exc:
            session.rollback()
            _set_meta_message_status(session, message.message_id, "failed", error=str(exc))
            log.exception(
                "Meta background processing failed chat_hash=%s message_id=%s elapsed_ms=%.1f",
                chat_hash,
                message.message_id,
                _elapsed_ms(request_start),
            )


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
    background_tasks: BackgroundTasks,
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
    try:
        raw_body = await request.body()
    except ClientDisconnect:
        log.warning(
            "Meta webhook client disconnected before request body was read elapsed_ms=%.1f", _elapsed_ms(request_start)
        )
        return Response(content="Client disconnected", status_code=499)

    signature_header = request.headers.get("x-hub-signature-256")
    if not _verify_meta_signature(
        raw_body,
        signature_header,
        settings.meta_app_secret,
    ):
        log.warning("Rejected Meta webhook POST with invalid signature elapsed_ms=%.1f", _elapsed_ms(request_start))
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
        log.info("Meta webhook received no message bytes=%s elapsed_ms=%.1f", len(raw_body), _elapsed_ms(request_start))
        return Response(content="ok", media_type="text/plain")

    chat_hash = _identifier_hash(message.chat_id, settings.meta_app_secret)
    log.info(
        "Meta inbound message queued chat_hash=%s message_id=%s kind=%s text_prefix=%r text_len=%s has_image=%s",
        chat_hash,
        message.message_id,
        message.kind,
        _text_prefix(message.text),
        len(message.text),
        bool(message.image_ref),
    )
    if not _enqueue_meta_message(session, message.message_id, chat_hash):
        log.info(
            "Meta webhook duplicate acknowledged chat_hash=%s elapsed_ms=%.1f", chat_hash, _elapsed_ms(request_start)
        )
        return Response(content="ok", media_type="text/plain")

    background_tasks.add_task(
        _process_meta_message_background,
        body,
        settings,
        matcher,
        notifier,
        conversation_store,
    )
    log.info("Meta webhook acknowledged chat_hash=%s elapsed_ms=%.1f", chat_hash, _elapsed_ms(request_start))
    return Response(content="ok", media_type="text/plain")
