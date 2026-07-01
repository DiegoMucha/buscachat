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


# Palabras que aparecen en cedulas venezolanas pero no son parte del nombre.
_NAME_NOISE_WORDS = frozenset({
    "edo", "civil", "soltero", "soltera", "casado", "casada",
    "divorciado", "divorciada", "viudo", "viuda",
    "director", "directora", "directorjefe", "jefe",
    "dr", "dra", "doctor", "doctora", "lic", "licenciado", "licenciada",
    "republica", "bolivariana", "venezuela", "venezolano", "venezolana",
    "cedula", "identidad", "nacionalidad", "estado",
    "fecha", "nacimiento", "sexo", "firma", "huella",
    "nombres", "apellidos", "nombre", "apellido",
})

# Nombres/apellidos comunes en Venezuela para separar palabras concatenadas por OCR.
_COMMON_NAMES = frozenset({
    "JUAN", "JOSE", "MARIA", "ANGELA", "ALVARO", "JUNIOR", "ENRIQUE",
    "CARLOS", "LUIS", "PEDRO", "ANA", "CARMEN", "ROSA", "MIGUEL",
    "ANTONIO", "JESUS", "DANIEL", "DAVID", "ANDRES", "FERNANDO",
    "JAVIER", "ALBERTO", "DIEGO", "EDUARDO", "MARTIN", "FERNANDA",
    "GONZALEZ", "GARCIA", "RODRIGUEZ", "LOPEZ", "MARTINEZ", "PEREZ",
    "SANABRIA", "ROJAS", "DIAZ", "TARAZONA", "LEIVA", "FLORES",
    "RAMIREZ", "TORRES", "RIVERA", "GOMEZ", "SANCHEZ", "HERNANDEZ",
    "RAMOS", "MORALES", "CRUZ", "REYES", "DURAN", "MENDOZA", "CASTRO",
})


_NAME_LABEL_RE = re.compile(
    r"(apellidos?|nombres?|apell|pell|apel|ellido|pellid|nomb|ombre|mbre|nomeres?)",
    re.IGNORECASE,
)
_APELLIDO_LABEL_RE = re.compile(r"(apellidos?|apell|pell|apel|ellido|pellid)", re.IGNORECASE)
_NOMBRE_LABEL_RE = re.compile(r"(nombres?|nomb|ombre|mbre|nomeres?)", re.IGNORECASE)
_CEDULA_LIKE_RE = re.compile(r"^[VE]\s*[-.]?\s*\d|\d{1,2}[.]\d{3}[.]\d{3}")


def _is_valid_name_line(candidate: str) -> bool:
    """Una linea es candidata a nombre si tiene palabras validas y no es cedula/ruido."""
    words = candidate.split()
    if not words:
        return False
    if _CEDULA_LIKE_RE.search(candidate):
        return False
    # Rechazar si TODAS las palabras son ruido (ej: "EDO CIVIL").
    return not all(w.lower() in _NAME_NOISE_WORDS for w in words)


def _strip_label_residual(value: str, matched_label_len: int) -> str:
    """Quita residuos cortos del label.

    Si OCR leyo el label completo (ej: 'APELLIDOS') no tocamos el valor,
    salvo una 's' suelta residual del plural (ej: OMBRES -> OMBRE + S).
    Si fue parcial (ej: 'PELL' en 'PELLDOsLEIVA') quitamos el fragmento.
    """
    value = value.strip()
    if matched_label_len < 5:
        value = re.sub(r"^\s*[A-Za-z]{1,3}[sS]?\s*", "", value).strip()
    # Quitar 's' suelta residual (no remove 'S' de un nombre como Sandra).
    value = re.sub(r"^\s*[sS]\b\s*", "", value).strip()
    return value


def _split_concatenated_word(word: str) -> str:
    """Intenta separar palabras fusionadas por OCR usando un diccionario reducido.

    Ejemplo: 'SANABRIAROJAS' -> 'SANABRIA ROJAS', 'JUNIORENRIQUE' -> 'JUNIOR ENRIQUE'.
    """
    if len(word) <= 10 or not word.isalpha():
        return word
    w = word.upper()
    # Preferir prefijo conocido.
    for name in sorted(_COMMON_NAMES, key=len, reverse=True):
        if w.startswith(name) and len(w) > len(name) + 2:
            rest = w[len(name):]
            if rest in _COMMON_NAMES or len(rest) >= 3:
                return f"{name} {rest}"
    # Si no hay prefijo, probar sufijo conocido.
    for name in sorted(_COMMON_NAMES, key=len, reverse=True):
        if w.endswith(name) and len(w) > len(name) + 2:
            prefix = w[:-len(name)]
            if prefix in _COMMON_NAMES or len(prefix) >= 3:
                return f"{prefix} {name}"
    return word


def _extract_after_label(line: str, match: re.Match) -> str:
    """Extrae el valor despues de un label garbado.

    Cuando label y valor estan separados por espacio solo recorta espacios.
    Cuando estan pegados intenta quitar el residuo corto del label.
    """
    after = line[match.end():]
    if after and not after[0].isspace():
        after = _strip_label_residual(after, len(match.group(0)))
    return after.strip()


def _clean_name(s: str) -> str:
    """Limpia puntuacion, numeros sueltos, palabras ruido y separa palabras fusionadas."""
    if not s:
        return ""
    s = re.sub(r"[-_.:,;]+", " ", s)
    words = []
    for w in s.split():
        if re.match(r"^\d+$", w):
            continue
        if w.lower() in _NAME_NOISE_WORDS:
            continue
        words.extend(_split_concatenated_word(w).split())
    return " ".join(words)


def _split_concatenated_name_line(line: str) -> tuple[str, str] | None:
    """Separa APELLIDOS y NOMBRES cuando OCR los fusiona en una linea.

    Ejemplo: 'PELLDOsLEIVA GONZALEZ OMBRES ANGELA MARIA'
      -> apellidos='LEIVA GONZALEZ', nombres='ANGELA MARIA'
    """
    ll = line.lower()
    apell_match = _APELLIDO_LABEL_RE.search(ll)
    nomb_match = _NOMBRE_LABEL_RE.search(ll)

    if not apell_match or not nomb_match:
        return None

    apell_label_len = apell_match.end() - apell_match.start()
    nomb_label_len = nomb_match.end() - nomb_match.start()

    if apell_match.start() < nomb_match.start():
        apell_value = line[apell_match.end():nomb_match.start()]
        nomb_value = line[nomb_match.end():]
    else:
        nomb_value = line[nomb_match.end():apell_match.start()]
        apell_value = line[apell_match.end():]

    apellidos = _strip_label_residual(apell_value, apell_label_len)
    nombres = _strip_label_residual(nomb_value, nomb_label_len)
    return apellidos, nombres


def _find_name(lines: list[str], full_text: str) -> str | None:
    """Busca nombre completo en cedula venezolana.

    Soporta:
      - Labels y valores en lineas separadas (formato estandar).
      - Label y valor en la misma linea (ej: 'APELUDOs PINA MENDEZ').
      - Labels concatenados en una sola linea por OCR.
    """
    log.info("OCR lines: %s", lines)
    nombres = ""
    apellidos = ""

    for i, line in enumerate(lines):
        original_line = line
        ll = line.lower()

        # Caso concatenado: APELLIDOS + NOMBRES en una sola linea.
        if _APELLIDO_LABEL_RE.search(ll) and _NOMBRE_LABEL_RE.search(ll):
            split = _split_concatenated_name_line(original_line)
            if split:
                apellidos, nombres = split
                continue

        # Label de NOMBRES -> primero inline, luego siguiente linea valida.
        nomb_match = _NOMBRE_LABEL_RE.search(ll)
        if nomb_match:
            cleaned = _extract_after_label(original_line, nomb_match).strip()
            if cleaned:
                nombres = cleaned
            else:
                for j in range(i + 1, min(i + 4, len(lines))):
                    candidate = lines[j].strip()
                    if _is_valid_name_line(candidate):
                        nombres = candidate
                        break
            continue

        # Label de APELLIDOS -> primero inline, luego siguiente linea valida.
        apell_match = _APELLIDO_LABEL_RE.search(ll)
        if apell_match:
            cleaned = _extract_after_label(original_line, apell_match).strip()
            if cleaned:
                apellidos = cleaned
            else:
                for j in range(i + 1, min(i + 4, len(lines))):
                    candidate = lines[j].strip()
                    if _is_valid_name_line(candidate):
                        apellidos = candidate
                        break
            continue

    nombres = _clean_name(nombres)
    apellidos = _clean_name(apellidos)

    # Evitar duplicados si un valor contiene al otro (ej: tras limpieza).
    if nombres and apellidos and nombres.lower() in apellidos.lower():
        apellidos = re.sub(re.escape(nombres), "", apellidos, flags=re.IGNORECASE).strip()
        apellidos = re.sub(r"\s+", " ", apellidos).strip()
    elif nombres and apellidos and apellidos.lower() in nombres.lower():
        nombres = re.sub(re.escape(apellidos), "", nombres, flags=re.IGNORECASE).strip()
        nombres = re.sub(r"\s+", " ", nombres).strip()

    log.info("OCR name: nombres=%r apellidos=%r", nombres, apellidos)

    if nombres and apellidos:
        return f"{nombres} {apellidos}"
    if nombres:
        return nombres
    if apellidos:
        return apellidos

    # Fallback: las 2 lineas mas largas que parecen nombres.
    skip = [r"^\d", r"VENEZOLANO", r"REPUBLICA", r"BOLIVARIANA", r"CEDULA",
            r"NACIONALIDAD", r"ESTADO", r"FECHA", r"SEXO", r"FIRMA", r"HUELLA",
            r"V-", r"E-", r"DIRECTOR", r"SOLTERO", r"CASADO", r"EDO", r"F\\.",
            r"NOMBRE", r"APELLIDO", r"\bDr\b", r"\bDra\b",
            r"(nomb|apell|pellid)"]
    candidates = [
        _clean_name(line)
        for line in lines
        if not any(re.search(p, line, re.IGNORECASE) for p in skip)
    ]
    candidates = [c for c in candidates if len(c.split()) >= 2]
    log.info("OCR fallback: %s", candidates[:3])
    if len(candidates) >= 2:
        # En cedulas venezolanas APELLIDOS aparece antes que NOMBRES;
        # devolvemos en formato nombres apellidos.
        return f"{candidates[1]} {candidates[0]}"
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
            # Asegurar el guion: V12345678 -> V-12345678
            cedula = re.sub(r"^([VE])(\d+)$", r"\1-\2", cedula)
            return cedula

    return None


def _find_birth_date(lines: list[str], full_text: str) -> str | None:
    """Busca fecha de nacimiento y normaliza el separador a '/'."""
    match = re.search(r"(\d{2}[/-]\d{2}[/-]\d{2,4})", full_text)
    return match.group(1).replace("-", "/") if match else None
