"""
Splitter de texto largo en ventanas de tamaño acotado, con solape.

Se usa cuando un fragmento natural (una subsección de procedimiento, una
entrada de tabla inusualmente larga) supera el `chunk_size` configurado para
su tipo de documento. Divide por límites de frase cuando puede, para no
cortar una idea a mitad, y nunca por mitad de palabra.
"""

from __future__ import annotations

import re

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")
_LIST_ITEM_START_RE = re.compile(r"^(?:\d+[.)]|[-*])\s+")


def _split_into_blocks(text: str) -> list[str]:
    """
    Separa el texto en bloques naturales por línea: cada ítem de una lista
    numerada ('1. ...') o con viñetas ('- ...') inicia un bloque nuevo: el
    resto se agrupa como prosa continua.

    Esto evita que el split por frases confunda un marcador de lista ('2.')
    con el punto final de una oración, que es lo que pasaba al tratar todo
    el texto como prosa plana.
    """
    lines = text.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if _LIST_ITEM_START_RE.match(line.strip()) and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        joined = "\n".join(current).strip()
        if joined:
            blocks.append(joined)
    return blocks


def _split_into_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_BOUNDARY_RE.split(text) if s]


def _build_units(text: str, chunk_size: int) -> list[str]:
    """Unidades de empaquetado: bloques (ítems de lista/párrafos) enteros si caben, si no, sus frases."""
    units: list[str] = []
    for block in _split_into_blocks(text):
        if len(block) <= chunk_size:
            units.append(block)
        else:
            units.extend(_split_into_sentences(block))
    return units


def split_with_overlap(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    Divide `text` en fragmentos de hasta `chunk_size` caracteres, con `chunk_overlap`
    caracteres de contexto repetidos entre fragmentos consecutivos.

    Si el texto completo ya cabe en `chunk_size`, se devuelve como un único
    fragmento (no se fragmenta innecesariamente). La división respeta límites
    de frase siempre que sea posible.

    Args:
        text: Texto a dividir.
        chunk_size: Tamaño máximo objetivo por fragmento, en caracteres.
        chunk_overlap: Caracteres de solape deseados entre fragmentos consecutivos.

    Raises:
        ValueError: si chunk_size <= 0 o chunk_overlap >= chunk_size.
    """
    text = text.strip()
    if not text:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size debe ser mayor que 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap no puede ser negativo")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap debe ser menor que chunk_size")

    if len(text) <= chunk_size:
        return [text]

    units = _build_units(text, chunk_size)
    if not units:
        units = [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for unit in units:
        unit_len = len(unit) + (1 if current else 0)  # +1 por el espacio de unión
        if current and current_len + unit_len > chunk_size:
            chunks.append(" ".join(current))
            current, current_len = _carry_overlap(current, chunk_overlap)
        if len(unit) > chunk_size:
            # Una sola "frase" ya excede el tamaño máximo: partirla por palabras.
            for piece in _hard_split(unit, chunk_size):
                if current:
                    chunks.append(" ".join(current))
                    current, current_len = [], 0
                chunks.append(piece)
            continue
        current.append(unit)
        current_len += unit_len

    if current:
        chunks.append(" ".join(current))

    return chunks


def _carry_overlap(current: list[str], chunk_overlap: int) -> tuple[list[str], int]:
    """Conserva las últimas unidades de `current` hasta sumar ~chunk_overlap caracteres, para iniciar el siguiente chunk."""
    if chunk_overlap == 0:
        return [], 0
    carried: list[str] = []
    carried_len = 0
    for unit in reversed(current):
        added = len(unit) + (1 if carried else 0)
        if carried and carried_len + added > chunk_overlap:
            break
        carried.insert(0, unit)
        carried_len += added
    return carried, carried_len


def _hard_split(text: str, chunk_size: int) -> list[str]:
    """División de último recurso por palabras, para una unidad sin puntuación que excede chunk_size."""
    words = text.split(" ")
    pieces: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        added = len(word) + (1 if current else 0)
        if current and current_len + added > chunk_size:
            pieces.append(" ".join(current))
            current, current_len = [], 0
        current.append(word)
        current_len += added
    if current:
        pieces.append(" ".join(current))
    return pieces
