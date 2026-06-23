"""Test de integración de src/orchestration/pipeline.py."""

from __future__ import annotations

import pandas as pd
import pytest

from src.config import load_settings
from src.orchestration.metrics import RESULTADO_ACLARACION, RESULTADO_ESCALADA, RESULTADO_RESPONDIDA
from src.orchestration.pipeline import ask, submit_feedback
from tests.conftest import FakeEmbeddingClient, FakeGenerationClient


def _add(collection, chunk_id: str, text: str, vector: list[float], metadata: dict | None = None) -> None:
    collection.add(ids=[chunk_id], embeddings=[vector], documents=[text], metadatas=[metadata] if metadata else None)


@pytest.fixture
def settings(tmp_path):
    """Settings reales, pero con los logs de métricas redirigidos a tmp_path para no tocar metrics/ del repo."""
    base = load_settings()
    return base.__class__(
        **{
            **base.__dict__,
            "feedback_log_path": tmp_path / "feedback_log.csv",
            "gap_log_path": tmp_path / "gap_log.csv",
        }
    )


class TestAsk:
    def test_high_confidence_calls_generation_and_returns_its_text(self, cosine_collection, settings):
        _add(cosine_collection, "a", "procedimiento de overbooking", [1.0, 0.0], metadata={"doc_type": "directorios", "source_path": "docs/directorios/a.md"})
        embedding_client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})
        generation_client = FakeGenerationClient(response="aquí está la respuesta generada")

        result = ask("consulta", "directo", settings, embedding_client, cosine_collection, generation_client)

        assert result.text == "aquí está la respuesta generada"
        assert result.was_escalated is False
        assert result.sources == ["a.md"]
        assert len(generation_client.calls) == 1

    def test_low_confidence_escalates_without_calling_generation(self, cosine_collection, settings):
        _add(cosine_collection, "a", "tema no relacionado", [0.0, 1.0], metadata={"doc_type": "directorios"})
        embedding_client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})  # ortogonal -> similitud 0.0
        generation_client = FakeGenerationClient()

        result = ask("consulta", "directo", settings, embedding_client, cosine_collection, generation_client)

        assert result.was_escalated is True
        assert "No tengo información suficiente" in result.text
        assert generation_client.calls == []  # nunca se debe llamar al modelo si se escala

    def test_invalid_mode_raises_value_error(self, cosine_collection, settings):
        with pytest.raises(ValueError, match="mode"):
            ask("consulta", "modo-invalido", settings, FakeEmbeddingClient(), cosine_collection, FakeGenerationClient())

    def test_interaction_is_logged_with_correct_result(self, cosine_collection, settings):
        _add(cosine_collection, "a", "info", [1.0, 0.0], metadata={"doc_type": "directorios", "source_path": "docs/directorios/a.md"})
        embedding_client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})

        result = ask("consulta", "directo", settings, embedding_client, cosine_collection, FakeGenerationClient())

        df = pd.read_csv(settings.feedback_log_path, dtype=str)
        assert len(df) == 1
        assert df.iloc[0]["interaction_id"] == result.interaction_id
        assert df.iloc[0]["resultado"] == RESULTADO_RESPONDIDA
        assert df.iloc[0]["modo"] == "directo"

    def test_escalated_interaction_logged_in_gap_log_too(self, cosine_collection, settings):
        _add(cosine_collection, "a", "tema no relacionado", [0.0, 1.0])
        embedding_client = FakeEmbeddingClient(vectors={"consulta sin respuesta clara": [1.0, 0.0]})

        ask("consulta sin respuesta clara", "directo", settings, embedding_client, cosine_collection, FakeGenerationClient())

        assert settings.gap_log_path.exists()
        gap_df = pd.read_csv(settings.gap_log_path, dtype=str)
        assert gap_df.iloc[0]["pregunta"] == "consulta sin respuesta clara"

    def test_returned_interaction_id_can_receive_feedback(self, cosine_collection, settings):
        _add(cosine_collection, "a", "info", [1.0, 0.0], metadata={"doc_type": "directorios"})
        embedding_client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})
        result = ask("consulta", "directo", settings, embedding_client, cosine_collection, FakeGenerationClient())

        submit_feedback(result.interaction_id, "correcto", settings)

        df = pd.read_csv(settings.feedback_log_path, dtype=str)
        assert df.iloc[0]["feedback"] == "correcto"

    def test_clarification_response_logged_with_its_own_resultado(self, cosine_collection, settings):
        _add(cosine_collection, "a", "info de overbooking", [1.0, 0.0], metadata={"doc_type": "procedimientos", "modo": "directo", "source_path": "docs/procedimientos/overbooking.md"})
        embedding_client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})
        generation_client = FakeGenerationClient(response="ACLARACIÓN: ¿el huésped ya llegó al hotel?")

        result = ask("consulta", "directo", settings, embedding_client, cosine_collection, generation_client)

        assert result.is_clarification is True
        assert result.was_escalated is False
        assert result.text == "¿el huésped ya llegó al hotel?"
        assert result.sources == []

        df = pd.read_csv(settings.feedback_log_path, dtype=str)
        assert df.iloc[0]["resultado"] == RESULTADO_ACLARACION

    def test_clarification_not_logged_to_gap_log(self, cosine_collection, settings):
        _add(cosine_collection, "a", "info", [1.0, 0.0], metadata={"doc_type": "directorios"})
        embedding_client = FakeEmbeddingClient(vectors={"consulta": [1.0, 0.0]})
        generation_client = FakeGenerationClient(response="ACLARACIÓN: ¿confirmas el dato?")

        ask("consulta", "directo", settings, embedding_client, cosine_collection, generation_client)

        assert not settings.gap_log_path.exists()

    def test_history_passed_through_ask_to_retrieval_and_generation(self, cosine_collection, settings):
        _add(cosine_collection, "a", "info de overbooking", [1.0, 0.0], metadata={"doc_type": "procedimientos", "modo": "directo", "source_path": "docs/procedimientos/overbooking.md"})
        combined_query = "¿qué hago con un overbooking? ¿el huésped ya llegó al hotel? ya llegó"
        embedding_client = FakeEmbeddingClient(vectors={combined_query: [1.0, 0.0]})
        generation_client = FakeGenerationClient(response="Contacta al huésped por teléfono.")
        history = [("user", "¿qué hago con un overbooking?"), ("assistant", "¿el huésped ya llegó al hotel?")]

        result = ask("ya llegó", "directo", settings, embedding_client, cosine_collection, generation_client, history=history)

        assert result.was_escalated is False
        _, user_prompt = generation_client.calls[0]
        assert "CONVERSACIÓN PREVIA" in user_prompt
