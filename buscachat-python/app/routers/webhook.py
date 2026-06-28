import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from app.database import get_session
from app.models import WebhookEventLog
from app.security import require_private_token

router = APIRouter(prefix="/whatsapp-webhook", tags=["whatsapp-webhook"])


class WebhookCaptureResponse(BaseModel):
    ok: bool = True
    log_id: int


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


@router.api_route(
    "",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    response_model=WebhookCaptureResponse,
    summary="Capture any WhatsApp webhook event without authentication",
)
async def capture_whatsapp_webhook_event(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> WebhookCaptureResponse:
    event_log = WebhookEventLog(
        method=request.method,
        url=str(request.url),
        path=request.url.path,
        source_ip=_source_ip(request),
        headers=dict(request.headers),
        query_params=_query_params(request),
        body=await _request_body(request),
    )
    session.add(event_log)
    session.commit()
    session.refresh(event_log)
    return WebhookCaptureResponse(log_id=event_log.id)


@router.get(
    "/logs",
    response_model=list[WebhookEventLog],
    summary="List captured WhatsApp webhook events",
)
def list_whatsapp_webhook_logs(
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
    summary="Delete all captured WhatsApp webhook events",
)
def delete_whatsapp_webhook_logs(
    session: Annotated[Session, Depends(get_session)],
) -> WebhookDeleteResponse:
    result = session.exec(delete(WebhookEventLog))
    session.commit()
    return WebhookDeleteResponse(deleted=result.rowcount or 0)
