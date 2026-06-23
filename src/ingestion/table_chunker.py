"""
Chunker para documentos tabulares: directorios de contacto e inventarios.

Ambos tipos de documento comparten exactamente la misma forma estructural
(ver docs/decisiones/0004-chunking-tabular-compartido.md): título H1,
metadatos, varias secciones H2 que contienen una tabla markdown, y una
sección final de notas sin tabla. Por eso usan el mismo chunker — la
diferencia entre "directorios" e "inventarios" es solo el valor de doc_type
y las rutas de origen, no la lógica de chunking.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.ingestion.markdown_parser import (
    extract_bullets,
    parse_markdown_table,
    slugify,
    split_by_heading,
)
from src.ingestion.models import Chunk
from src.ingestion.text_splitter import split_with_overlap

logger = logging.getLogger(__name__)


def _row_has_content(row: dict[str, str], key_column: str) -> bool:
    """Una fila aporta información recuperable si algún campo más allá de la columna clave tiene valor."""
    return any(value.strip() for column, value in row.items() if column != key_column and value.strip())


_MISSING_VALUE = "no disponible"


def _row_to_text(row: dict[str, str]) -> str:
    """
    Convierte una fila de tabla en una frase autocontenida en lenguaje natural, apta para embeddings.

    Las columnas vacías se renderizan como "no disponible" en vez de omitirse:
    si el chunk simplemente no menciona "Teléfono", el modelo generador no
    tiene forma de distinguir "este dato no está documentado" de "esta
    columna no aplica a esta fila", y puede acabar usando un campo vecino
    (p. ej. el horario) como si fuera la respuesta a una pregunta sobre el
    campo ausente.
    """
    parts = [f"{column}: {value.strip() or _MISSING_VALUE}" for column, value in row.items()]
    return ". ".join(parts) + "."


def chunk_table_document(
    text: str,
    doc_type: str,
    source_path: Path,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """
    Genera los Chunks de un documento tabular (directorio o inventario).

    Por cada sección H2: si contiene una tabla, una fila con contenido real
    se convierte en un chunk (una fila vacía de plantilla se descarta). Si la
    sección no contiene tabla (p. ej. "Notas de mantenimiento"), cada viñeta
    de nivel superior se convierte en un chunk.

    Filas o viñetas inusualmente largas se subdividen con `split_with_overlap`
    respetando chunk_size/chunk_overlap, igual que el resto del pipeline.
    """
    if doc_type not in {"directorios", "inventarios", "referencias"}:
        raise ValueError(f"doc_type no soportado por chunk_table_document: {doc_type!r}")

    chunks: list[Chunk] = []

    # Tema del documento, derivado del primer H1: se antepone a cada chunk para
    # reforzar a qué documento pertenece (ver docs/decisiones/0016). Sin esto, una
    # fila como "Coffee español: Coffee break bebida" no lleva ninguna señal de que
    # pertenece al documento de facturación, y compite mal con documentos genéricos.
    h1_blocks = split_by_heading(text, level=1)
    doc_topic = h1_blocks[0].title if h1_blocks else source_path.stem

    sections = split_by_heading(text, level=2)

    if not sections:
        logger.warning("No se encontraron secciones H2 en %s; documento omitido", source_path)
        return []

    for section in sections:
        rows = parse_markdown_table(section.body)
        section_slug = slugify(section.title)

        if rows:
            key_column = next(iter(rows[0]), "")
            kept = 0
            for row_index, row in enumerate(rows):
                if not _row_has_content(row, key_column):
                    continue
                row_text = _row_to_text(row)
                row_text = f"[{doc_topic}] {row_text}"
                pieces = split_with_overlap(row_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                for piece_index, piece in enumerate(pieces):
                    chunks.append(
                        Chunk(
                            text=piece,
                            doc_type=doc_type,
                            source_path=source_path,
                            chunk_id=f"{source_path.stem}::{section_slug}::{row_index}::{piece_index}",
                            metadata={
                                "categoria": section.title,
                                "tipo_entrada": "tabla",
                            },
                        )
                    )
                kept += 1
            if kept == 0:
                logger.info(
                    "Sección '%s' de %s no tiene filas con datos reales (solo plantilla vacía); 0 chunks generados",
                    section.title,
                    source_path,
                )
        else:
            bullets = extract_bullets(section.body)
            if not bullets:
                logger.warning(
                    "Sección '%s' de %s no tiene tabla ni viñetas (probablemente texto en prosa); "
                    "0 chunks generados. Si quieres que se indexe, conviértela en viñetas.",
                    section.title,
                    source_path,
                )
            for bullet_index, bullet in enumerate(bullets):
                bullet = f"[{doc_topic}] {bullet}"
                pieces = split_with_overlap(bullet, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                for piece_index, piece in enumerate(pieces):
                    chunks.append(
                        Chunk(
                            text=piece,
                            doc_type=doc_type,
                            source_path=source_path,
                            chunk_id=f"{source_path.stem}::{section_slug}::nota::{bullet_index}::{piece_index}",
                            metadata={
                                "categoria": section.title,
                                "tipo_entrada": "nota",
                            },
                        )
                    )

    return chunks