"""Tests de src/retrieval/confidence.py."""

from __future__ import annotations

from src.retrieval.confidence import evaluate
from src.retrieval.search import SearchResult


def _result(chunk_id: str, similarity: float) -> SearchResult:
    return SearchResult(chunk_id=chunk_id, text=f"texto {chunk_id}", similarity=similarity, metadata={})


class TestEvaluate:
    def test_best_result_above_threshold_should_answer(self):
        decision = evaluate([_result("a", 0.8), _result("b", 0.5)], confidence_threshold=0.65)
        assert decision.should_answer is True
        assert decision.best_result.chunk_id == "a"
        assert decision.confidence == 0.8

    def test_best_result_below_threshold_should_escalate(self):
        decision = evaluate([_result("a", 0.4)], confidence_threshold=0.65)
        assert decision.should_answer is False
        assert decision.confidence == 0.4

    def test_best_result_exactly_at_threshold_should_answer(self):
        """El umbral es inclusivo: igual al umbral cuenta como confianza suficiente."""
        decision = evaluate([_result("a", 0.65)], confidence_threshold=0.65)
        assert decision.should_answer is True

    def test_no_results_should_escalate(self):
        decision = evaluate([], confidence_threshold=0.65)
        assert decision.should_answer is False
        assert decision.best_result is None
        assert decision.confidence == 0.0

    def test_only_best_result_matters_even_if_others_are_high(self):
        """Solo se evalúa el primer resultado (el más similar); los demás no pueden 'salvar' la decisión."""
        decision = evaluate([_result("a", 0.3), _result("b", 0.9)], confidence_threshold=0.65)
        assert decision.should_answer is False  # "a" es el primero (se asume ya ordenado), no "b"

    def test_results_preserved_in_decision_even_when_escalating(self):
        """El resto de resultados se conservan en la decisión aunque se escale; útil para el gap log."""
        results = [_result("a", 0.4), _result("b", 0.3)]
        decision = evaluate(results, confidence_threshold=0.65)
        assert decision.results == results
