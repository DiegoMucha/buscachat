from app.config import Settings
from app.face.base import Embedding, FaceMatcher, cosine_similarity
from app.face.stub import StubFaceMatcher

__all__ = [
    "Embedding",
    "FaceMatcher",
    "StubFaceMatcher",
    "cosine_similarity",
    "get_face_matcher",
]


def get_face_matcher(settings: Settings) -> FaceMatcher:
    """Return the configured face matcher.

    ``insightface`` uses the local ONNX model; ``stub`` uses a dependency-free
    deterministic matcher (handy for tests and environments without the native
    libraries installed).
    """
    if settings.face_matcher == "stub":
        return StubFaceMatcher()

    from app.face.insightface_matcher import InsightFaceMatcher  # noqa: PLC0415

    return InsightFaceMatcher(model_name=settings.face_insightface_model)
