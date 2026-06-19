"""
Modelo de datos común producido por la capa de ingesta.

`Chunk` es el contrato entre `ingestion` y el resto del pipeline (embeddings,
retrieval). Ningún otro módulo de ingesta debería exponer una estructura de
datos distinta hacia afuera: si cambia el chunking interno, esta forma se
mantiene estable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Chunk:
    """Un fragmento de documento listo para generar su embedding.

    Attributes:
        text: Texto final del fragmento, en lenguaje natural autocontenido
            (no markdown crudo), listo para pasar al modelo de embeddings.
        doc_type: Categoría del documento de origen: "procedimientos",
            "directorios" o "inventarios".
        source_path: Ruta del archivo fuente, usada para citar la fuente en
            la respuesta final.
        chunk_id: Identificador estable y único del chunk dentro de todo el
            corpus. Debe ser determinista entre ejecuciones (mismo input ->
            mismo id) para que reindexar sea una actualización, no una
            duplicación, en ChromaDB.
        metadata: Campos adicionales específicos del tipo de documento
            (p. ej. categoría, subsección, modo). Todos los valores deben
            ser tipos simples (str/int/float/bool), compatibles con los
            metadatos de ChromaDB.
    """

    text: str
    doc_type: str
    source_path: Path
    chunk_id: str
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError(f"Chunk vacío para chunk_id={self.chunk_id!r}")
        if not self.chunk_id:
            raise ValueError("chunk_id no puede estar vacío")
