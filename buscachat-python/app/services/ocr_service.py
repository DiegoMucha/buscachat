"""Servicio OCR para extraer datos de cédulas venezolanas usando PaddleOCR."""

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# PaddleOCR se importa lazy para no cargarlo si no se usa
_ocr_reader = None


def _get_reader():
    global _ocr_reader
    if _ocr_reader is None:
        from paddleocr import PaddleOCR
        _ocr_reader = PaddleOCR(lang="es", use_angle_cls=True, show_log=False)
    return _ocr_reader


def extract_text_from_image(image_bytes: bytes) -> str:
    """Extrae todo el texto de una imagen (lista manuscrita, etc.)."""
    try:
        reader = _get_reader()
        result = reader.ocr(image_bytes, cls=True)
    except Exception:
        log.exception("PaddleOCR text extraction failed")
        return ""

    if not result or not result[0]:
        return ""

    lines = []
    for line_group in result[0]:
        text = line_group[1][0] if line_group[1] else ""
        if text.strip():
            lines.append(text.strip())

    return "\n".join(lines)


def extract_from_id_image(image_bytes: bytes) -> dict[str, Any]:
    """Extrae nombre, cédula y fecha de nacimiento de una imagen de cédula."""
    try:
        reader = _get_reader()
        result = reader.ocr(image_bytes, cls=True)
    except Exception:
        log.exception("PaddleOCR failed")
        return {}

    if not result or not result[0]:
        return {}

    # Extraer todo el texto en orden
    lines = []
    for line_group in result[0]:
        text = line_group[1][0] if line_group[1] else ""
        if text.strip():
            lines.append(text.strip())

    full_text = "\n".join(lines)
    log.info("OCR text: %s", full_text[:200])

    return {
        "nombre": _find_name(lines, full_text),
        "cedula": _find_cedula(lines, full_text),
        "fecha_nacimiento": _find_birth_date(lines, full_text),
        "raw_text": full_text,
    }


def _find_name(lines: list[str], full_text: str) -> str | None:
    """Busca el nombre en el texto OCR de cédula venezolana."""
    # Patrón: "NOMBRES" o "NOMBRE" seguido de texto
    for i, line in enumerate(lines):
        if re.search(r"NOMBRE", line, re.IGNORECASE):
            # El nombre suele estar en la misma línea o la siguiente
            name_line = line if len(line.split()) > 2 else (lines[i + 1] if i + 1 < len(lines) else "")
            name_line = re.sub(r"(?i)NOMBRES?:?\s*", "", name_line).strip()
            if name_line:
                return name_line

    # Fallback: buscar línea con formato "Nombre Apellido"
    for line in lines:
        words = line.split()
        if 2 <= len(words) <= 6 and all(w[0].isupper() for w in words if w):
            # Evitar líneas que son solo números o códigos
            if not re.search(r"^\d", line) and not re.search(r"VENEZOLANO|REPUBLICA|CEDULA", line, re.IGNORECASE):
                return line

    return None


def _find_cedula(lines: list[str], full_text: str) -> str | None:
    """Busca número de cédula en formato venezolano."""
    # Patrones: V-12345678, V 12.345.678, E-12345678
    patterns = [
        r"[VE]\s*[-.]?\s*\d{1,2}[.]?\d{3}[.]?\d{3}",
        r"C[ÉE]DULA\s*:?\s*([VE]\s*[-.]?\s*\d{1,2}[.]?\d{3}[.]?\d{3})",
        r"\d{1,2}[.]\d{3}[.]\d{3}",
    ]

    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            cedula = match.group(0) if "CÉDULA" not in match.group(0).upper() else match.group(1)
            # Normalizar a V-12345678
            cedula = cedula.upper().strip()
            cedula = re.sub(r"[.\s]+", "", cedula)
            if not cedula.startswith(("V", "E")):
                cedula = "V" + cedula
            return cedula

    return None


def _find_birth_date(lines: list[str], full_text: str) -> str | None:
    """Busca fecha de nacimiento."""
    match = re.search(r"(\d{2}[/-]\d{2}[/-]\d{2,4})", full_text)
    return match.group(1) if match else None
