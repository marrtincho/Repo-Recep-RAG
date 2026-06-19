"""
Utilidades genéricas de parseo markdown.

Este módulo no sabe nada del dominio hotelero: solo entiende markdown
(encabezados, tablas, viñetas, líneas de metadatos en negrita). Los chunkers
de cada tipo de documento (`table_chunker.py`, `procedure_chunker.py`)
construyen la lógica específica encima de estas piezas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BOLD_KEY_VALUE_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*\S)\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?[\s:|-]+\|[\s:|-]*\|?$")
_HR_RE = re.compile(r"^-{3,}$")


def slugify(text: str) -> str:
    """Normaliza un título a una forma estable para usar en IDs (sin acentos, en minúsculas, con guiones)."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_only = ascii_only.lower().strip()
    ascii_only = re.sub(r"[^a-z0-9]+", "-", ascii_only)
    return ascii_only.strip("-")


@dataclass(frozen=True)
class HeadingBlock:
    """Un bloque de texto bajo un encabezado markdown de un nivel dado."""

    level: int
    title: str
    body: str  # todo el contenido hasta el siguiente encabezado del MISMO nivel (incluye sub-encabezados anidados)


def split_by_heading(text: str, level: int) -> list[HeadingBlock]:
    """
    Divide `text` en bloques delimitados por encabezados de un nivel exacto (p. ej. nivel=1 para '# ').

    Texto antes del primer encabezado de ese nivel se descarta (es preámbulo,
    no pertenece a ningún bloque con nombre). Los encabezados de otros niveles
    quedan dentro del `body` del bloque, sin procesar — eso lo hace quien
    llame a esta función si necesita anidar otro split_by_heading.
    """
    lines = text.splitlines()
    blocks: list[HeadingBlock] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        if current_title is not None:
            blocks.append(HeadingBlock(level=level, title=current_title, body="\n".join(current_lines).strip()))

    for line in lines:
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) == level:
            _flush()
            current_title = match.group(2).strip()
            current_lines = []
        else:
            if current_title is not None:
                current_lines.append(line)
    _flush()

    return blocks


def leading_text_before_any_heading(body: str) -> str:
    """
    Devuelve solo las líneas de `body` anteriores al primer encabezado anidado de cualquier nivel.

    Útil para aislar el preámbulo/metadatos de un bloque sin arrastrar
    accidentalmente contenido de sub-secciones anidadas (p. ej. evitar que
    una plantilla con valores de ejemplo dentro de un '##' anidado se
    confunda con metadatos reales del bloque padre).
    """
    lines = []
    for line in body.splitlines():
        if _HEADING_RE.match(line):
            break
        lines.append(line)
    return "\n".join(lines)


def parse_metadata_block(text: str) -> dict[str, str]:
    """
    Extrae pares clave-valor de líneas con formato '**Clave:** valor'.

    Las claves se normalizan con `slugify` y guiones convertidos a guion bajo
    (p. ej. '**Última actualización:**' -> 'ultima_actualizacion').
    Líneas que no matchean el patrón se ignoran.
    """
    metadata: dict[str, str] = {}
    for line in text.splitlines():
        match = _BOLD_KEY_VALUE_RE.match(line.strip())
        if match:
            key = slugify(match.group(1)).replace("-", "_")
            value = match.group(2).strip()
            metadata[key] = value
    return metadata


def extract_bullets(text: str) -> list[str]:
    """Devuelve la lista de viñetas ('- ' o '* ') de nivel superior encontradas en `text`."""
    bullets = []
    for line in text.splitlines():
        match = _BULLET_RE.match(line.strip())
        if match:
            bullets.append(match.group(1).strip())
    return bullets


def parse_markdown_table(text: str) -> list[dict[str, str]]:
    """
    Parsea la primera tabla markdown encontrada en `text` y devuelve una fila por dict.

    Las claves de cada dict son los nombres de columna (cabecera), tal cual
    aparecen en el markdown, sin normalizar (la normalización es decisión de
    quien consume la tabla, no de este parser genérico). Devuelve lista vacía
    si no hay ninguna tabla.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if _TABLE_SEPARATOR_RE.match(stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 1:
        return []

    header = rows[0]
    data_rows = rows[1:]
    result = []
    for row in data_rows:
        # Tolerar filas con menos celdas que la cabecera (markdown mal alineado a mano)
        padded = row + [""] * (len(header) - len(row))
        result.append(dict(zip(header, padded[: len(header)])))
    return result


def strip_horizontal_rules(text: str) -> str:
    """Elimina líneas que son únicamente separadores visuales ('---'), preservando el resto del texto."""
    return "\n".join(line for line in text.splitlines() if not _HR_RE.match(line.strip()))
