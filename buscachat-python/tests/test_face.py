from app.config import Settings
from app.face import StubFaceMatcher, cosine_similarity, get_face_matcher


def test_cosine_similarity_identical_and_orthogonal() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_stub_matcher_is_deterministic_and_distinct() -> None:
    matcher = StubFaceMatcher()

    a1 = matcher.embed(b"face-a")
    a2 = matcher.embed(b"face-a")
    b = matcher.embed(b"face-b")

    assert a1 is not None and b is not None
    assert len(a1) == matcher.dimensions
    assert a1 == a2
    assert cosine_similarity(a1, a2) == 1.0
    assert cosine_similarity(a1, b) < 0.35
    assert matcher.embed(b"") is None


def test_get_face_matcher_selects_stub() -> None:
    settings = Settings(face_matcher="stub")
    assert isinstance(get_face_matcher(settings), StubFaceMatcher)
