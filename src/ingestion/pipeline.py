"""
Punto de entrada público de la capa de ingesta.

`run_ingestion` es la única función que el resto del sistema (capa de
embeddings, scripts de indexado) debería llamar. Internamente decide qué
chunker usar según el tipo de documento y agrega los resultados; quien la
llama no necesita saber que existen dos chunkers distintos por debajo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.config import Settings
from src.ingestion.models import Chunk
from src.ingestion.procedure_chunker import chunk_procedure_document
from src.ingestion.table_chunker import chunk_table_document

logger = logging.getLogger(__name__)

TABLE_DOC_TYPES = {"directorios", "inventarios", "referencias"}
PROCEDURE_DOC_TYPES = {"procedimientos"}


def _chunk_document(text: str, doc_type: str, source_path: Path, settings: Settings) -> list[Chunk]:
    profile = settings.chunking[doc_type]
    if doc_type in TABLE_DOC_TYPES:
        return chunk_table_document(
            text, doc_type, source_path,
            chunk_size=profile.chunk_size, chunk_overlap=profile.chunk_overlap,
        )
    if doc_type in PROCEDURE_DOC_TYPES:
        return chunk_procedure_document(
            text, source_path,
            chunk_size=profile.chunk_size, chunk_overlap=profile.chunk_overlap,
        )
    raise ValueError(f"No hay chunker registrado para doc_type={doc_type!r}")


def load_documents(settings: Settings) -> list[Chunk]:
    """
    Recorre las carpetas de documentos configuradas y devuelve todos los Chunks generados.

    Cada subcarpeta de `settings.doc_type_paths` se procesa con el chunker
    correspondiente a su tipo. Una carpeta inexistente se trata como "sin
    documentos todavía" (se avisa, no se lanza error) para no romper un
    proyecto recién clonado antes de añadir contenido.
    """
    all_chunks: list[Chunk] = []

    for doc_type, folder in settings.doc_type_paths.items():
        if not folder.exists():
            logger.warning("Carpeta de documentos no encontrada para '%s': %s", doc_type, folder)
            continue

        md_files = sorted(folder.glob("*.md"))
        if not md_files:
            logger.info("No hay documentos .md en %s (tipo '%s') todavía", folder, doc_type)
            continue

        for path in md_files:
            text = path.read_text(encoding="utf-8")
            chunks = _chunk_document(text, doc_type, path, settings)
            logger.info("Ingestados %d chunks desde %s", len(chunks), path.name)
            all_chunks.extend(chunks)

    return all_chunks