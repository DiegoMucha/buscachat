from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.adapters.green_api import Notifier
from app.config import Settings, get_settings
from app.database import get_session
from app.face import FaceMatcher
from app.messaging.adapters.green_api import adapt_green_api_message
from app.messaging.dependencies import (
    get_conversation_state_store_dependency,
    get_face_matcher_dependency,
    get_notifier_dependency,
)
from app.messaging.pipeline import run_message_pipeline
from app.messaging.session_store import ConversationStateStore

router = APIRouter(
    prefix="/whatsapp-green-api-webhook",
    tags=["whatsapp-green-api-webhook"],
)


class WebhookResponse(BaseModel):
    chat_id: str
    text: str
    accion: str | None = None
    buttons: list[dict[str, str]] = []


@router.post("")
def whatsapp_green_api_webhook(
    body: dict,
    session: Annotated[Session, Depends(get_session)],
    matcher: Annotated[FaceMatcher, Depends(get_face_matcher_dependency)],
    notifier: Annotated[Notifier, Depends(get_notifier_dependency)],
    conversation_store: Annotated[
        ConversationStateStore,
        Depends(get_conversation_state_store_dependency),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebhookResponse:
    message = adapt_green_api_message(body)
    outbound = run_message_pipeline(
        message,
        session=session,
        matcher=matcher,
        notifier=notifier,
        settings=settings,
        conversation_store=conversation_store,
    )
    return WebhookResponse(
        chat_id=outbound.chat_id,
        text=outbound.text,
        accion=outbound.action,
        buttons=[button.model_dump() for button in outbound.buttons],
    )
