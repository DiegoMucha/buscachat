"""Tests para el parser OCR de cedulas venezolanas.

Los datos son ficticios para no filtrar informacion personal.
"""

import pytest

from app.services.ocr_service import (
    _find_birth_date,
    _find_cedula,
    _find_name,
    _split_concatenated_name_line,
)


def test_standard_separate_lines() -> None:
    lines = [
        "REPUBLICA BOLIVARIANA DE VENEZUELA",
        "CEDULA DE IDENTIDAD",
        "APELLIDOS: LOPEZ MARTINEZ",
        "NOMBRES: CARLOS ANDRES",
        "C.I. V-11.222.333",
    ]
    assert _find_name(lines, "\n".join(lines)) == "CARLOS ANDRES LOPEZ MARTINEZ"


def test_inline_apellidos_label() -> None:
    lines = [
        "APELLIDOS LOPEZ MARTINEZ",
        "NOMBRES CARLOS ANDRES",
    ]
    assert _find_name(lines, "\n".join(lines)) == "CARLOS ANDRES LOPEZ MARTINEZ"


def test_concatenated_apellidos_and_nombres() -> None:
    lines = ["PELLDOsPEREZ RAMIREZ OMBRES MARIA FERNANDA"]
    assert _find_name(lines, "\n".join(lines)) == "MARIA FERNANDA PEREZ RAMIREZ"


def test_split_concatenated_name_line_helper() -> None:
    apellidos, nombres = _split_concatenated_name_line("PELLDOsPEREZ RAMIREZ OMBRES MARIA FERNANDA")
    assert apellidos == "PEREZ RAMIREZ"
    assert nombres == "MARIA FERNANDA"


def test_marital_status_noise_removed() -> None:
    lines = [
        "APELLIDOS TORRES MORALES",
        "NOMBRES LUIS EDUARDO",
        "ESTADO CIVIL SOLTERO",
        "EDO CIVIL",
    ]
    assert _find_name(lines, "\n".join(lines)) == "LUIS EDUARDO TORRES MORALES"


def test_name_line_with_noise_words_is_skipped() -> None:
    lines = [
        "NOMBRES ANDRES TORRES EDO CIVIL",
        "APELLIDOS SANCHEZ LOPEZ",
    ]
    result = _find_name(lines, "\n".join(lines))
    assert result == "ANDRES TORRES SANCHEZ LOPEZ"


def test_find_cedula_variants() -> None:
    assert _find_cedula([], "C.I. V-11.222.333") == "V-11222333"
    assert _find_cedula([], "Cedula: V 12.345.678") == "V-12345678"
    assert _find_cedula([], "E-98765432") == "E-98765432"
    assert _find_cedula([], "9.876.543") == "V-9876543"


def test_find_birth_date() -> None:
    assert _find_birth_date([], "FECHA DE NACIMIENTO 28/02/1998") == "28/02/1998"
    assert _find_birth_date([], "28-02-1998") == "28/02/1998"


def test_full_label_no_over_strip() -> None:
    # El label completo 'APELLIDOS' fue leido; no debe cortar el inicio del apellido.
    # Los valores vienen pegados al label pero en lineas separadas.
    lines = [
        "APELLIDOSMENDOZACASTRO",
        "NOMERESJAVIERALBERTO",
    ]
    assert _find_name(lines, "\n".join(lines)) == "JAVIER ALBERTO MENDOZA CASTRO"


def test_single_word_first_name() -> None:
    lines = [
        "APELLIDOS RAMOS REYES",
        "NOMBRES DIEGO",
    ]
    assert _find_name(lines, "\n".join(lines)) == "DIEGO RAMOS REYES"


def test_nombres_ocr_garbled_nomeres() -> None:
    lines = [
        "APELLIDOS MENDOZA CASTRO",
        "NOMERES JAVIER ALBERTO",
    ]
    assert _find_name(lines, "\n".join(lines)) == "JAVIER ALBERTO MENDOZA CASTRO"


def test_fallback_ignores_director_and_other_noise() -> None:
    lines = [
        "REPUBLICA BOLIVARIANA DE VENEZUELA",
        "DIRECTOR",
        "SAIME",
        "V-12345678",
    ]
    assert _find_name(lines, "\n".join(lines)) is None


def test_fallback_splits_concatenated_apellidos_and_ignores_dr() -> None:
    # Simula caso 2: apellidos fusionados sin label, con linea del Director.
    lines = [
        "CEDULA DE IDENTIDAD",
        "V-11.222.333",
        "PEREZRAMIREZ",
        "Dr.Martin Flores",
        "MARIA FERNANDA",
        "Director",
        "08/01/2003",
    ]
    assert _find_name(lines, "\n".join(lines)) == "MARIA FERNANDA PEREZ RAMIREZ"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
