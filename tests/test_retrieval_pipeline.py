"""Test de integración de src/retrieval/pipeline.py — une search + confidence."""

from __future__ import annotations

from src.config import load_settings
from src.retrieval.pipeline import retrieve
from tests.conftest import FakeEmbeddingClient


def _add(collection, chunk_id: str, text: str, vector: list[float], metadata: dict | None = None) -> None:
    collection.add(ids=[chunk_id], embeddings=[vector], documents=[text], metadatas=[metadata] if metadata else None)


class TestRetrieve:
    def test_uses_settings_top_k_and_threshold(self, cosine_collection):
        settings = load_settings()
        _add(cosine_collection, "a", "respuesta clara", [1.0, 0.0], metadata={"doc_type": "directorios"})
        client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})

        decision = retrieve("consulta", settings, client, cosine_collection)

        assert decision.should_answer is True
        assert decision.confidence_threshold == settings.confidence_threshold

    def test_low_similarity_results_in_escalation(self, cosine_collection):
        _add(cosine_collection, "a", "tema no relacionado", [0.0, 1.0], metadata={"doc_type": "directorios"})
        settings = load_settings()
        client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})  # ortogonal -> similitud 0.0

        decision = retrieve("consulta", settings, client, cosine_collection)

        assert decision.should_answer is False

    def test_history_enriches_search_query(self, cosine_collection):
        """Con historial, la consulta de búsqueda real debe combinar los turnos previos, no solo el mensaje actual."""
        _add(cosine_collection, "a", "info", [1.0, 0.0], metadata={"doc_type": "directorios"})
        settings = load_settings()
        client = FakeEmbeddingClient(vectors={"¿qué hago con un overbooking? ¿el huésped ya llegó? ya llegó": [1.0, 0.0]})

        retrieve(
            "ya llegó",
            settings,
            client,
            cosine_collection,
            history=[("user", "¿qué hago con un overbooking?"), ("assistant", "¿el huésped ya llegó?")],
        )

        assert client.calls == [["¿qué hago con un overbooking? ¿el huésped ya llegó? ya llegó"]]

    def test_no_history_uses_query_unchanged(self, cosine_collection):
        _add(cosine_collection, "a", "info", [1.0, 0.0], metadata={"doc_type": "directorios"})
        settings = load_settings()
        client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})

        retrieve("consulta", settings, client, cosine_collection, history=None)

        assert client.calls == [["consulta"]]
