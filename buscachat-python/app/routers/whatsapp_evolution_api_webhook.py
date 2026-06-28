import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from app.adapters.green_api import Notifier
from app.config import Settings, get_settings
from app.database import get_session
from app.face import FaceMatcher
from app.messaging.adapters.evolution_api import (
    EvolutionApiAuthenticationError,
    adapt_evolution_api_message,
    redact_evolution_api_secret,
    require_evolution_api_key,
)
from app.messaging.dependencies import (
    get_face_matcher_dependency,
    get_notifier_dependency,
)
from app.messaging.pipeline import run_message_pipeline
from app.models import WebhookEventLog
from app.security import require_private_token

router = APIRouter(
    prefix="/whatsapp-evolution-api-webhook",
    tags=["whatsapp-evolution-api-webhook"],
)


class WebhookCaptureResponse(BaseModel):
    ok: bool = True
    log_id: int
    ignored: bool = False
    chat_id: str | None = None
    text: str | None = None
    accion: str | None = None
    buttons: list[dict[str, str]] = []


class WebhookDeleteResponse(BaseModel):
    ok: bool = True
    deleted: int


def _source_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return None


def _query_params(request: Request) -> dict[str, Any]:
    return {
        key: values if len(values) > 1 else values[0]
        for key in request.query_params
        for values in [request.query_params.getlist(key)]
    }


async def _request_body(request: Request) -> Any | None:
    raw_body = await request.body()
    if not raw_body:
        return None

    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body.decode("utf-8", errors="replace")


def _store_event_log(
    request: Request,
    session: Session,
    body: Any | None,
) -> WebhookEventLog:
    event_log = WebhookEventLog(
        method=request.method,
        url=str(request.url),
        path=request.url.path,
        source_ip=_source_ip(request),
        headers=dict(request.headers),
        query_params=_query_params(request),
        body=redact_evolution_api_secret(body),
    )
    session.add(event_log)
    session.commit()
    session.refresh(event_log)
    return event_log


@router.post(
    "",
    response_model=WebhookCaptureResponse,
    summary="Receive Evolution API WhatsApp messages",
)
async def whatsapp_evolution_api_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dependency)],
    notifier: Annotated[Notifier, Depends(get_notifier_dependency)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebhookCaptureResponse:
    body = await _request_body(request)
    event_log = _store_event_log(request, session, body)

    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON body required")

    try:
        require_evolution_api_key(body, settings)
    except EvolutionApiAuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    message = adapt_evolution_api_message(body)
    if message is None:
        return WebhookCaptureResponse(log_id=event_log.id, ignored=True)

    outbound = run_message_pipeline(
        message,
        session=session,
        matcher=matcher,
        notifier=notifier,
        settings=settings,
    )
    return WebhookCaptureResponse(
        log_id=event_log.id,
        chat_id=outbound.chat_id,
        text=outbound.text,
        accion=outbound.action,
        buttons=[button.model_dump() for button in outbound.buttons],
    )


@router.get(
    "/logs",
    response_model=list[WebhookEventLog],
    summary="List captured Evolution API webhook events",
)
def list_whatsapp_evolution_api_webhook_logs(
    session: Annotated[Session, Depends(get_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[WebhookEventLog]:
    statement = (
        select(WebhookEventLog)
        .order_by(WebhookEventLog.created_at.desc(), WebhookEventLog.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(statement).all())


@router.delete(
    "/logs",
    response_model=WebhookDeleteResponse,
    dependencies=[Depends(require_private_token)],
    summary="Delete all captured Evolution API webhook events",
)
def delete_whatsapp_evolution_api_webhook_logs(
    session: Annotated[Session, Depends(get_session)],
) -> WebhookDeleteResponse:
    result = session.exec(delete(WebhookEventLog))
    session.commit()
    return WebhookDeleteResponse(deleted=result.rowcount or 0)
