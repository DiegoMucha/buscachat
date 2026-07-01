from app.services.search import _cedula_digits, _looks_like_cedula


def test_cedula_detection_accepts_common_venezuelan_formats() -> None:
    assert _cedula_digits("V-11.222.333") == "11222333"
    assert _cedula_digits("Cedula: E 9 876 543") == "9876543"
    assert _looks_like_cedula("V-11.222.333") is True
    assert _looks_like_cedula("11222333") is True


def test_cedula_detection_rejects_short_or_empty_text() -> None:
    assert _looks_like_cedula("abc") is False
    assert _looks_like_cedula("1234") is False
