"""
Búsqueda semántica sobre la colección de ChromaDB.

Convierte una consulta en texto a embedding y recupera los chunks más
similares. La distancia coseno que devuelve ChromaDB se convierte aquí mismo
a similitud (1 - distancia, ver docs/decisiones/0006), para que el resto del
sistema (confidence.py, orchestration) trabaje siempre en términos de
similitud, nunca de distancia cruda.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class EmbeddingClient(Protocol):
    """Contrato mínimo que esta capa necesita de un cliente de embeddings."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class SearchResult:
    """Un resultado de búsqueda: el chunk recuperado, su similitud y sus metadatos."""

    chunk_id: str
    text: str
    similarity: float
    metadata: dict[str, Any]


def search(
    query: str,
    embedding_client: EmbeddingClient,
    collection,
    top_k: int,
    where: dict[str, Any] | None = None,
) -> list[SearchResult]:
    """
    Busca los `top_k` chunks más similares a `query` en `collection`.

    `where` permite filtrar por metadata de ChromaDB si hace falta (por
    ejemplo, por doc_type). El retrieval ya no filtra por modo (ver ADR
    0011): trae lo más relevante sin importar la subsección del documento.
    """
    if not query.strip():
        raise ValueError("La consulta no puede estar vacía")
    if top_k <= 0:
        raise ValueError("top_k debe ser mayor que 0")

    [embedding] = embedding_client.embed_batch([query])

    response = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    ids = response["ids"][0]
    documents = response["documents"][0]
    metadatas = response["metadatas"][0]
    distances = response["distances"][0]

    return [
        SearchResult(
            chunk_id=chunk_id,
            text=document,
            similarity=1.0 - distance,
            metadata=dict(metadata) if metadata else {},
        )
        for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances)
    ]
