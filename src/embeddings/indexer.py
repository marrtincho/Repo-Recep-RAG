"""
Indexador: genera embeddings de los Chunks de ingesta y los persiste en ChromaDB.

La indexación es idempotente y sincronizada (ver
docs/decisiones/0005-indexado-idempotente-con-poda.md): reindexar el mismo
corpus no duplica nada (usa los chunk_id estables de la capa de ingesta vía
`collection.upsert`), y cualquier chunk_id que ya no exista en el corpus
actual se elimina de la colección, para que el índice nunca quede con
entradas obsoletas que ya no reflejan docs/.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import chromadb

from src.config import Settings
from src.ingestion.models import Chunk

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 64
DEFAULT_COLLECTION_NAME = "hotel_recepcion"


class EmbeddingClient(Protocol):
    """Contrato mínimo que el indexador necesita de un cliente de embeddings."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


def _chunk_to_metadata(chunk: Chunk) -> dict[str, str]:
    """Aplana doc_type y source_path junto al resto de metadata, todo como valores simples (str)."""
    return {
        "doc_type": chunk.doc_type,
        "source_path": str(chunk.source_path),
        **chunk.metadata,
    }


DISTANCE_METRIC = "cosine"


def get_collection(
    chroma_db_path: Path, collection_name: str = DEFAULT_COLLECTION_NAME
) -> chromadb.Collection:
    """
    Abre (o crea) la colección persistida en `chroma_db_path`, con métrica coseno.

    La métrica se fija explícitamente (`hnsw:space: cosine`) porque el
    umbral de confianza en settings.yaml se interpreta como similitud
    coseno en [0, 1] (más alto = mejor) — ver
    docs/decisiones/0006-metrica-coseno-para-confianza.md. El valor por
    defecto de ChromaDB es L2, que rompería esa semántica en silencio si no
    se fija aquí.

    Si la colección ya existía con otra métrica (p. ej. creada antes de
    fijar esto explícitamente), se lanza un error claro en vez de dejar que
    el umbral de confianza dé resultados sin sentido sin avisar.
    """
    chroma_db_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_db_path))
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": DISTANCE_METRIC},
    )

    actual_metric = collection.metadata.get("hnsw:space", "l2") if collection.metadata else "l2"
    if actual_metric != DISTANCE_METRIC:
        raise ValueError(
            f"La colección '{collection_name}' en {chroma_db_path} ya existe con métrica "
            f"'{actual_metric}', pero el sistema espera '{DISTANCE_METRIC}'. El umbral de "
            f"confianza no tendría el significado esperado. Borra data/chroma_db/ y reindexa "
            f"desde cero con 'python scripts/reindex.py'."
        )

    return collection


def index_chunks(
    chunks: list[Chunk],
    embedding_client: EmbeddingClient,
    collection: chromadb.Collection,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """
    Genera embeddings para `chunks` y sincroniza la colección de ChromaDB con ellos.

    Returns:
        Resumen {"upserted": N, "deleted": M}, útil para logging y para el
        gap log / panel de métricas más adelante.
    """
    current_ids = {chunk.chunk_id for chunk in chunks}
    upserted = 0

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        embeddings = embedding_client.embed_batch([c.text for c in batch])
        if len(embeddings) != len(batch):
            raise ValueError(
                f"El cliente de embeddings devolvió {len(embeddings)} vectores "
                f"para {len(batch)} textos; deben coincidir uno a uno."
            )
        collection.upsert(
            ids=[c.chunk_id for c in batch],
            embeddings=embeddings,
            documents=[c.text for c in batch],
            metadatas=[_chunk_to_metadata(c) for c in batch],
        )
        upserted += len(batch)
        logger.info("Indexados %d/%d chunks", upserted, len(chunks))

    deleted = _prune_stale_ids(collection, current_ids)
    return {"upserted": upserted, "deleted": deleted}


def _prune_stale_ids(collection: chromadb.Collection, current_ids: set[str]) -> int:
    """Elimina de la colección cualquier id que ya no esté en el corpus actual."""
    existing = collection.get(include=[])  # los ids siempre se devuelven; no hace falta traer vectores/documentos
    stale_ids = [doc_id for doc_id in existing["ids"] if doc_id not in current_ids]
    if stale_ids:
        collection.delete(ids=stale_ids)
        logger.info("Eliminados %d chunks obsoletos del índice (ya no existen en docs/)", len(stale_ids))
    return len(stale_ids)


def index_documents(settings: Settings) -> dict[str, int]:
    """
    Punto de entrada de alto nivel: carga y chunkea docs/, genera embeddings y sincroniza ChromaDB.

    Es la función que debería llamar un script de indexado (`scripts/reindex.py`)
    o un futuro botón "Reindexar" en la interfaz de Streamlit.
    """
    from src.embeddings.ollama_client import OllamaEmbeddingClient
    from src.ingestion.pipeline import load_documents

    chunks = load_documents(settings)
    if not chunks:
        logger.warning("No hay chunks para indexar; ¿docs/ está vacío?")
        return {"upserted": 0, "deleted": 0}

    embedding_client = OllamaEmbeddingClient(model=settings.embedding_model, host=settings.ollama_host)
    collection = get_collection(settings.chroma_db_path)
    return index_chunks(chunks, embedding_client, collection)
