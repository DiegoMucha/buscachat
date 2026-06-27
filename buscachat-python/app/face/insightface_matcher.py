import logging

from app.face.base import Embedding

log = logging.getLogger(__name__)


class InsightFaceMatcher:
    """Face matcher backed by a local InsightFace (ONNX) model.

    The native dependencies (``insightface``, ``onnxruntime``, ``opencv``,
    ``numpy``) are imported lazily on first use so importing the app does not pay
    the model load cost and does not fail when the optional libraries are absent.
    """

    def __init__(self, model_name: str = "buffalo_l") -> None:
        self.model_name = model_name
        self._app = None

    def _ensure_loaded(self) -> None:
        if self._app is not None:
            return

        from insightface.app import FaceAnalysis  # noqa: PLC0415

        app = FaceAnalysis(name=self.model_name)
        app.prepare(ctx_id=-1)  # CPU
        self._app = app
        log.info("InsightFace model '%s' loaded", self.model_name)

    def embed(self, image_bytes: bytes) -> Embedding | None:
        if not image_bytes:
            return None

        import cv2  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        self._ensure_loaded()
        assert self._app is not None

        buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            log.warning("Could not decode image bytes for face embedding")
            return None

        faces = self._app.get(image)
        if not faces:
            return None

        # Pick the largest detected face by bounding-box area.
        def _area(face) -> float:
            box = face.bbox
            return float((box[2] - box[0]) * (box[3] - box[1]))

        best = max(faces, key=_area)
        embedding = getattr(best, "normed_embedding", None)
        if embedding is None:
            embedding = best.embedding
        return [float(x) for x in embedding]
