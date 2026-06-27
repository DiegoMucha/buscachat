import math
from typing import Protocol, runtime_checkable

Embedding = list[float]


@runtime_checkable
class FaceMatcher(Protocol):
    """Interface for face-embedding backends.

    Implementations turn an image into a face embedding. Returning ``None`` means
    no usable face was detected in the image.
    """

    def embed(self, image_bytes: bytes) -> Embedding | None:
        raise NotImplementedError


def cosine_similarity(a: Embedding, b: Embedding) -> float:
    """Cosine similarity between two embeddings, in ``[-1, 1]``.

    Returns ``0.0`` when either vector is empty or has zero magnitude.
    """
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
