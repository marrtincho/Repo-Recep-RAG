"""Tests de src/retrieval/search.py — vectores construidos a mano para similitud coseno predecible."""

from __future__ import annotations

import pytest

from src.retrieval.search import search
from tests.conftest import FakeEmbeddingClient


def _add(collection, chunk_id: str, text: str, vector: list[float], metadata: dict | None = None) -> None:
    collection.add(ids=[chunk_id], embeddings=[vector], documents=[text], metadatas=[metadata] if metadata else None)


class TestSearch:
    def test_returns_results_ordered_by_similarity_descending(self, cosine_collection):
        _add(cosine_collection, "a", "vector identico", [1.0, 0.0])
        _add(cosine_collection, "b", "vector ortogonal", [0.0, 1.0])
        _add(cosine_collection, "c", "vector opuesto", [-1.0, 0.0])
        client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})

        results = search("consulta", client, cosine_collection, top_k=3)

        assert [r.chunk_id for r in results] == ["a", "b", "c"]
        assert results[0].similarity == pytest.approx(1.0, abs=1e-6)
        assert results[1].similarity == pytest.approx(0.0, abs=1e-6)
        assert results[2].similarity == pytest.approx(-1.0, abs=1e-6)

    def test_respects_top_k(self, cosine_collection):
        _add(cosine_collection, "a", "uno", [1.0, 0.0])
        _add(cosine_collection, "b", "dos", [0.9, 0.1])
        _add(cosine_collection, "c", "tres", [0.0, 1.0])
        client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})

        results = search("consulta", client, cosine_collection, top_k=2)

        assert len(results) == 2

    def test_empty_query_raises_value_error(self, cosine_collection):
        with pytest.raises(ValueError, match="vacía"):
            search("   ", FakeEmbeddingClient(), cosine_collection, top_k=3)

    def test_invalid_top_k_raises_value_error(self, cosine_collection):
        with pytest.raises(ValueError, match="top_k"):
            search("consulta", FakeEmbeddingClient(), cosine_collection, top_k=0)

    def test_where_filter_is_applied(self, cosine_collection):
        _add(cosine_collection, "a", "directorio", [1.0, 0.0], metadata={"doc_type": "directorios"})
        _add(cosine_collection, "b", "procedimiento", [1.0, 0.0], metadata={"doc_type": "procedimientos"})
        client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})

        results = search("consulta", client, cosine_collection, top_k=5, where={"doc_type": "directorios"})

        assert [r.chunk_id for r in results] == ["a"]

    def test_metadata_propagated_in_result(self, cosine_collection):
        _add(cosine_collection, "a", "texto", [1.0, 0.0], metadata={"categoria": "Emergencias"})
        client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})

        results = search("consulta", client, cosine_collection, top_k=1)

        assert results[0].metadata["categoria"] == "Emergencias"

    def test_empty_collection_returns_empty_list(self, cosine_collection):
        client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})
        assert search("consulta", client, cosine_collection, top_k=3) == []

    def test_chunk_without_metadata_does_not_crash_search(self, cosine_collection):
        """Regresión: ChromaDB devuelve None (no {}) para una entrada sin metadata."""
        _add(cosine_collection, "a", "sin metadata", [1.0, 0.0], metadata=None)
        client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})

        results = search("consulta", client, cosine_collection, top_k=1)

        assert results[0].metadata == {}
