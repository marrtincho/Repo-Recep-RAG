"""Tests de src/generation/pipeline.py."""

from __future__ import annotations

import pytest

from src.generation.pipeline import generate_answer, select_context
from src.retrieval.confidence import RetrievalDecision
from src.retrieval.search import SearchResult
from tests.conftest import FakeGenerationClient


def _result(chunk_id: str, similarity: float, source_path: str = "docs/procedimientos/overbooking.md") -> SearchResult:
    return SearchResult(chunk_id=chunk_id, text=f"texto {chunk_id}", similarity=similarity, metadata={"source_path": source_path})


def _decision(results: list[SearchResult], threshold: float = 0.65, should_answer: bool | None = None) -> RetrievalDecision:
    best = results[0] if results else None
    answer = should_answer if should_answer is not None else (best is not None and best.similarity >= threshold)
    return RetrievalDecision(should_answer=answer, best_result=best, results=results, confidence_threshold=threshold)


class TestSelectContext:
    def test_filters_out_results_below_threshold(self):
        decision = _decision([_result("a", 0.9), _result("b", 0.3)], threshold=0.65)
        context = select_context(decision)
        assert [r.chunk_id for r in context] == ["a"]

    def test_keeps_all_results_above_threshold(self):
        decision = _decision([_result("a", 0.9), _result("b", 0.8)], threshold=0.65)
        context = select_context(decision)
        assert [r.chunk_id for r in context] == ["a", "b"]

    def test_empty_results_returns_empty_context(self):
        decision = _decision([], threshold=0.65)
        assert select_context(decision) == []


class TestGenerateAnswer:
    def test_raises_if_should_answer_is_false(self):
        decision = _decision([_result("a", 0.9)], should_answer=False)
        with pytest.raises(ValueError, match="should_answer"):
            generate_answer("pregunta", "directo", decision, FakeGenerationClient())

    def test_returns_generated_text_and_mode(self):
        decision = _decision([_result("a", 0.9)])
        client = FakeGenerationClient(response="aquí está tu respuesta")
        answer = generate_answer("pregunta", "directo", decision, client)
        assert answer.text == "aquí está tu respuesta"
        assert answer.mode == "directo"

    def test_sources_extracted_from_context_filenames(self):
        decision = _decision([
            _result("a", 0.9, source_path="docs/procedimientos/overbooking.md"),
            _result("b", 0.8, source_path="docs/directorios/contactos.md"),
        ])
        answer = generate_answer("pregunta", "explicado", decision, FakeGenerationClient())
        assert answer.sources == ["contactos.md", "overbooking.md"]

    def test_sources_deduplicated(self):
        decision = _decision([
            _result("a", 0.9, source_path="docs/procedimientos/overbooking.md"),
            _result("b", 0.8, source_path="docs/procedimientos/overbooking.md"),
        ])
        answer = generate_answer("pregunta", "directo", decision, FakeGenerationClient())
        assert answer.sources == ["overbooking.md"]

    def test_low_confidence_secondary_results_excluded_from_sources(self):
        """Un resultado del top_k por debajo del umbral no debe aparecer citado como fuente."""
        decision = _decision([_result("a", 0.9), _result("b", 0.2)], threshold=0.65)
        answer = generate_answer("pregunta", "directo", decision, FakeGenerationClient())
        assert len(answer.sources) == 1

    def test_generation_client_receives_built_prompts(self):
        decision = _decision([_result("a", 0.9)])
        client = FakeGenerationClient()
        generate_answer("¿cómo gestiono un overbooking?", "explicado", decision, client)

        assert len(client.calls) == 1
        system_prompt, user_prompt = client.calls[0]
        assert "por qué" in system_prompt.lower()
        assert "¿cómo gestiono un overbooking?" in user_prompt

    def test_clarification_prefix_sets_flag_and_strips_prefix(self):
        decision = _decision([_result("a", 0.9)])
        client = FakeGenerationClient(response="ACLARACIÓN: ¿el huésped ya llegó al hotel?")

        answer = generate_answer("pregunta ambigua", "directo", decision, client)

        assert answer.is_clarification is True
        assert answer.text == "¿el huésped ya llegó al hotel?"
        assert "ACLARACIÓN" not in answer.text

    def test_clarification_response_has_no_sources(self):
        """No tiene sentido citar una fuente para una pregunta, no una respuesta basada en el contexto."""
        decision = _decision([_result("a", 0.9, source_path="docs/procedimientos/overbooking.md")])
        client = FakeGenerationClient(response="ACLARACIÓN: ¿qué tipo de habitación tenía reservada?")

        answer = generate_answer("pregunta", "directo", decision, client)

        assert answer.sources == []

    def test_clarification_detection_is_case_insensitive(self):
        decision = _decision([_result("a", 0.9)])
        client = FakeGenerationClient(response="aclaración: ¿confirmas el dato?")

        answer = generate_answer("pregunta", "directo", decision, client)

        assert answer.is_clarification is True

    def test_normal_answer_is_not_flagged_as_clarification(self):
        decision = _decision([_result("a", 0.9)])
        client = FakeGenerationClient(response="Esta es una respuesta normal y completa.")

        answer = generate_answer("pregunta", "directo", decision, client)

        assert answer.is_clarification is False
        assert answer.text == "Esta es una respuesta normal y completa."

    def test_history_passed_through_to_user_prompt(self):
        decision = _decision([_result("a", 0.9)])
        client = FakeGenerationClient()
        history = [("user", "¿qué hago con un overbooking?"), ("assistant", "¿el huésped ya llegó?")]

        generate_answer("ya llegó", "directo", decision, client, history=history)

        _, user_prompt = client.calls[0]
        assert "¿qué hago con un overbooking?" in user_prompt
        assert "CONVERSACIÓN PREVIA" in user_prompt
