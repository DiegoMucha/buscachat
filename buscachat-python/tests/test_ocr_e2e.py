"""Tests del OCR con imagenes reales de cedulas venezolanas.

Estos tests ejecutan PaddleOCR contra fixtures locales.
Estan excluidos de la corrida por defecto porque requieren paquetes opcionales
y pueden descargar modelos en el primer uso.

Para ejecutarlos:
    uv run --group ocr pytest -m ocr tests/test_ocr_e2e.py -v

Notas sobre los valores esperados:
- Imagen 1: el ultimo digito de la cedula no se distingue bien en la imagen;
  el test acepta V-24449876 o V-24449878.
- Imagen 2: el apellido se lee como LEIVA (confirmado por el usuario).
"""

import re
from pathlib import Path

import pytest

from app.services.ocr_service import extract_from_id_image

pytestmark = pytest.mark.ocr

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ocr"


@pytest.mark.parametrize(
    ("fixture_name", "expected_nombre", "expected_cedula_regex", "expected_fecha"),
    [
        (
            "cedula_1.jpg",
            "JUNIOR ENRIQUE SANABRIA ROJAS",
            r"^V-2444987[68]$",
            "16/03/1993",
        ),
        (
            "cedula_2.jpg",
            "ANGELA MARIA LEIVA GONZALEZ",
            r"^V-29790834$",
            "08/01/2003",
        ),
        (
            "cedula_3.jpg",
            "ALVARO DIAZ TARAZONA",
            r"^V-25712140$",
            "14/10/57",
        ),
    ],
)
def test_extract_from_real_cedula_image(
    fixture_name: str,
    expected_nombre: str,
    expected_cedula_regex: str,
    expected_fecha: str,
) -> None:
    image_bytes = (_FIXTURES_DIR / fixture_name).read_bytes()
    data = extract_from_id_image(image_bytes)

    assert data.get("nombre") == expected_nombre, f"raw_text: {data.get('raw_text')}"
    assert re.match(expected_cedula_regex, data.get("cedula", "")), (
        f"cedula={data.get('cedula')!r}, raw_text: {data.get('raw_text')}"
    )
    assert data.get("fecha_nacimiento") == expected_fecha, f"raw_text: {data.get('raw_text')}"
