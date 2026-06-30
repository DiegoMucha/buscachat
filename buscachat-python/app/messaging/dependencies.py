from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.face import FaceMatcher, get_face_matcher
from app.messaging.notifier import Notifier, get_notifier
from app.messaging.session_store import (
    ConversationStateStore,
    get_conversation_state_store,
)


@lru_cache
def _cached_face_matcher(face_matcher: str, model_name: str) -> FaceMatcher:
    settings = Settings(face_matcher=face_matcher, face_insightface_model=model_name)
    return get_face_matcher(settings)


def get_face_matcher_dependency(
    settings: Annotated[Settings, Depends(get_settings)],
) -> FaceMatcher:
    return _cached_face_matcher(settings.face_matcher, settings.face_insightface_model)


def get_notifier_dependency() -> Notifier:
    return get_notifier()


def get_conversation_state_store_dependency(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConversationStateStore:
    return get_conversation_state_store(settings)
