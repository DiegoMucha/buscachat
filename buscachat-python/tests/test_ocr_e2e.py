"""Tests e2e del OCR con imagenes reales de cedulas venezolanas.

Estos tests descargan imagenes desde URLs publicas y ejecutan PaddleOCR.
Por eso estan marcados como `e2e` y se excluyen de la corrida por defecto.

Para ejecutarlos:
    uv run pytest -m e2e tests/test_ocr_e2e.py -v

Notas sobre los valores esperados:
- Imagen 1: el ultimo digito de la cedula no se distingue bien en la imagen;
  el test acepta V-24449876 o V-24449878.
- Imagen 2: el apellido se lee como LEIVA (confirmado por el usuario).
"""

import re

import pytest

from app.services.ocr_service import extract_from_id_image

pytestmark = pytest.mark.e2e


# URLs publicas de cedulas venezolanas para validacion de OCR.
_CEDULA_1_URL = (
    "https://p16-ehi-sg.gauthstatic.com/tos-alisg-i-6e3a8cj6on-sg/"
    "f1de53e2fd45446a83fe48d03d8e966e~tplv-6e3a8cj6on-10.image"
)
_CEDULA_2_URL = (
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRTxxmueYfRpu_6aqKZS7MhmvYGaXBXmvZsaNRKX7jb3w&s=10"
)
_CEDULA_3_URL = (
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT9c_PRyMCyDpnniyTcN7ix0usTN3WiPjHo4CGFBXFLRA&s=10"
)


def _download_image(url: str) -> bytes:
    """Descarga una imagen; hace skip si no hay conexion."""
    try:
        import httpx

        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        return response.content
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"No se pudo descargar la imagen {url}: {exc}")


@pytest.mark.parametrize(
    ("url", "expected_nombre", "expected_cedula_regex", "expected_fecha"),
    [
        (
            _CEDULA_1_URL,
            "JUNIOR ENRIQUE SANABRIA ROJAS",
            r"^V-2444987[68]$",
            "16/03/1993",
        ),
        (
            _CEDULA_2_URL,
            "ANGELA MARIA LEIVA GONZALEZ",
            r"^V-29790834$",
            "08/01/2003",
        ),
        (
            _CEDULA_3_URL,
            "ALVARO DIAZ TARAZONA",
            r"^V-25712140$",
            "14/10/57",
        ),
    ],
)
def test_extract_from_real_cedula_image(
    url: str,
    expected_nombre: str,
    expected_cedula_regex: str,
    expected_fecha: str,
) -> None:
    image_bytes = _download_image(url)
    data = extract_from_id_image(image_bytes)

    assert data.get("nombre") == expected_nombre, f"raw_text: {data.get('raw_text')}"
    assert re.match(expected_cedula_regex, data.get("cedula", "")), (
        f"cedula={data.get('cedula')!r}, raw_text: {data.get('raw_text')}"
    )
    assert data.get("fecha_nacimiento") == expected_fecha, f"raw_text: {data.get('raw_text')}"
