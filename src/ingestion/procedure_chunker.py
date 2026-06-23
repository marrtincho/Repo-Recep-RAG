"""
Chunker para documentos de procedimiento operativo.

A diferencia de directorios/inventarios (ver table_chunker.py), un documento
de procedimientos no es tabular: cada procedimiento es un bloque H1 con un
bloque de metadatos (Categoría / Última actualización / Validado por) seguido
de subsecciones H3 (Resumen rápido, Procedimiento detallado, Casos
especiales, Cuándo escalar, Preguntas habituales, Notas internas).

La plantilla del propio formato (ver docs/decisiones/0003) establece que
"Resumen rápido" alimenta el modo directo del asistente y "Procedimiento
detallado" alimenta el modo explicado. Por eso cada chunk se etiqueta con
metadata["modo"], para que la capa de generación pueda filtrar por modo
cuando lo necesite.

Un mismo archivo .md puede mezclar bloques de plantilla genérica (sin
metadatos rellenados) con procedimientos reales. Un bloque H1 sin el
metadato mínimo requerido se considera plantilla/documentación de formato,
no un procedimiento operativo, y se omite (con aviso), en vez de indexarse
como si fuera conocimiento real.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.ingestion.markdown_parser import (
    leading_text_before_any_heading,
    parse_metadata_block,
    slugify,
    split_by_heading,
    strip_horizontal_rules,
)
from src.ingestion.models import Chunk
from src.ingestion.text_splitter import split_with_overlap

logger = logging.getLogger(__name__)

REQUIRED_METADATA_KEYS = {"categoria", "ultima_actualizacion", "validado_por"}

# Mapeo subsección -> modo de generación al que alimenta (ver docs/decisiones/0003).
# Cualquier subsección no listada aquí se considera válida para ambos modos.
SUBSECTION_MODE_MAP: dict[str, str] = {
    "resumen-rapido": "directo",
    "procedimiento-detallado": "explicado",
}
DEFAULT_MODE = "ambos"


def chunk_procedure_document(
    text: str,
    source_path: Path,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """
    Genera los Chunks de un documento de procedimientos.

    Cada bloque H1 se evalúa de forma independiente: si no tiene los
    metadatos mínimos (categoría, última actualización, validado por), se
    omite por completo y se registra un aviso — esto es lo que permite que
    un archivo mezcle plantilla genérica con procedimientos reales sin que
    la plantilla contamine el índice.
    """
    chunks: list[Chunk] = []
    blocks = split_by_heading(text, level=1)

    if not blocks:
        logger.warning("No se encontraron bloques H1 en %s; documento omitido", source_path)
        return []

    for block in blocks:
        preamble = leading_text_before_any_heading(block.body)
        metadata_block = parse_metadata_block(preamble)
        missing = REQUIRED_METADATA_KEYS - metadata_block.keys()

        if missing:
            logger.info(
                "Bloque '%s' de %s omitido: faltan metadatos requeridos %s "
                "(probablemente es texto de plantilla, no un procedimiento real)",
                block.title,
                source_path,
                sorted(missing),
            )
            continue

        subsections = split_by_heading(block.body, level=3)
        if not subsections:
            logger.warning(
                "Procedimiento '%s' de %s tiene metadatos pero ninguna subsección H3; documento omitido",
                block.title,
                source_path,
            )
            continue

        for subsection in subsections:
            mode = SUBSECTION_MODE_MAP.get(slugify(subsection.title), DEFAULT_MODE)
            body = strip_horizontal_rules(subsection.body).strip()
            if not body:
                continue

            pieces = split_with_overlap(body, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            for piece_index, piece in enumerate(pieces):
                topic = f"{metadata_block['categoria']} · {block.title}"
                chunk_text = f"[{topic}] {subsection.title}\n{piece}"
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        doc_type="procedimientos",
                        source_path=source_path,
                        chunk_id=(
                            f"{source_path.stem}::{slugify(block.title)}::"
                            f"{slugify(subsection.title)}::{piece_index}"
                        ),
                        metadata={
                            "nombre_procedimiento": block.title,
                            "categoria": metadata_block["categoria"],
                            "subseccion": subsection.title,
                            "modo": mode,
                            "ultima_actualizacion": metadata_block["ultima_actualizacion"],
                            "validado_por": metadata_block["validado_por"],
                        },
                    )
                )

    return chunks
