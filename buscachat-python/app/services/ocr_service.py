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
    """Busca nombre completo: APELLIDOS + NOMBRES (formato cedula venezolana).

    Tambien prueba buscar por posicion: en cedulas venezolanas,
    APELLIDOS suele estar en las primeras lineas despues de los datos de la republica.
    """
    nombres = ""
    apellidos = ""

    log.info("OCR lines: %s", lines)

    for i, line in enumerate(lines):
        # Detectar NOMBRES (flexible)
        if re.search(r"NOM(BRE|S)?S?", line, re.IGNORECASE):
            cleaned = re.sub(r"(?i)NOM(BRE|S)?S?:?\s*", "", line).strip()
            if cleaned and len(cleaned) > 2:
                nombres = cleaned
            elif i + 1 < len(lines):
                nombres = lines[i + 1].strip()

        # Detectar APELLIDOS (flexible: APEL, APELL, APELUDOs, etc.)
        for j, candidate in enumerate(lines):
            if re.search(r"APE(L{1,}|LL|LUDO)", candidate, re.IGNORECASE):
                # Limpiar todo desde APE hasta donde empiezan los apellidos reales
                cleaned = re.sub(r"(?i)APE(L{1,}|LL|LUDO)S?:?\s*", "", candidate).strip()
                if cleaned and len(cleaned) > 2:
                    apellidos = cleaned
                elif j + 1 < len(lines):
                    apellidos = lines[j + 1].strip()
                break

    log.info("OCR name: nombres=%r apellidos=%r", nombres, apellidos)

    # Limpiar ruido OCR (palabras cortas en mayusculas que no son nombres)
    def _clean(s: str) -> str:
        words = s.split()
        result = []
        for w in words:
            if len(w) < 2:
                continue
            # Filtrar palabras que son mayusculas con una minuscula al final (ruido OCR)
            upper_count = sum(1 for c in w if c.isupper())
            if len(w) == 4 and upper_count >= 3 and w[-1].islower():
                continue
            result.append(w)
        return " ".join(result)

    nombres = _clean(nombres)
    apellidos = _clean(apellidos)

    # Formato natural: NOMBRES APELLIDOS
    if apellidos and nombres:
        return f"{nombres} {apellidos}"
    if apellidos:
        return apellidos
    if nombres:
        return nombres

    # Ultimo fallback: agarrar las 2-3 lineas mas largas sin labels
    candidates = [l for l in lines if len(l.split()) >= 2 and not re.search(
        r"^\d|VENEZOLANO|REPUBLICA|BOLIVARIANA|CEDULA|NACIONALIDAD|ESTADO|FECHA|SEXO|NOMBRE|APELLIDO|FIRMA|HUELLA|V-|E-", l, re.IGNORECASE)]
    candidates.sort(key=len, reverse=True)
    log.info("OCR fallback: %s", candidates[:3])
    if len(candidates) >= 2:
        return f"{candidates[0]} {candidates[1]}"
    return candidates[0] if candidates else None


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
