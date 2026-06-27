import hashlib

from app.face.base import Embedding


class StubFaceMatcher:
    """Deterministic face matcher used for tests and dependency-free dev.

    It derives a fixed-length pseudo-embedding from the image bytes, so identical
    bytes yield identical embeddings (similarity 1.0) and different bytes yield
    different ones. It never imports heavy native libraries.
    """

    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions

    def embed(self, image_bytes: bytes) -> Embedding | None:
        if not image_bytes:
            return None

        values: list[float] = []
        counter = 0
        while len(values) < self.dimensions:
            digest = hashlib.sha256(image_bytes + counter.to_bytes(4, "big")).digest()
            for byte in digest:
                values.append((byte / 255.0) * 2.0 - 1.0)
                if len(values) >= self.dimensions:
                    break
            counter += 1
        return values
