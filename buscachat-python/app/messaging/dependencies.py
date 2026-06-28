from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.adapters.green_api import Notifier, get_notifier
from app.config import Settings, get_settings
from app.face import FaceMatcher, get_face_matcher


@lru_cache
def _cached_face_matcher(face_matcher: str, model_name: str) -> FaceMatcher:
    settings = Settings(face_matcher=face_matcher, face_insightface_model=model_name)
    return get_face_matcher(settings)


def get_face_matcher_dependency(
    settings: Annotated[Settings, Depends(get_settings)],
) -> FaceMatcher:
    return _cached_face_matcher(settings.face_matcher, settings.face_insightface_model)


def get_notifier_dependency(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Notifier:
    return get_notifier(settings)
