"""
Decisión de escalar/responder basada en el umbral de confianza configurado.

Esta es la capa 1 (algorítmica) del mecanismo de escalado de dos capas
descrito en el plan de acción: un umbral de similitud calibrado decide si
hay base suficiente para responder. La capa 2 (instrucción a nivel de
prompt) es una salvaguarda secundaria que vivirá en la capa de generación.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.retrieval.search import SearchResult


@dataclass(frozen=True)
class RetrievalDecision:
    """El resultado de evaluar una búsqueda contra el umbral de confianza."""

    should_answer: bool
    best_result: SearchResult | None
    results: list[SearchResult]
    confidence_threshold: float

    @property
    def confidence(self) -> float:
        """Similitud del mejor resultado, o 0.0 si la búsqueda no devolvió nada."""
        return self.best_result.similarity if self.best_result is not None else 0.0


def evaluate(results: list[SearchResult], confidence_threshold: float) -> RetrievalDecision:
    """
    Decide si hay confianza suficiente para responder, según el resultado más similar.

    `results` debe venir ya ordenado por similitud descendente (tal como lo
    devuelve `src.retrieval.search.search`). Solo se evalúa el primer
    resultado: si el mejor candidato no alcanza el umbral, ninguno de los
    siguientes (con similitud igual o menor) lo alcanzaría tampoco.
    """
    best_result = results[0] if results else None
    should_answer = best_result is not None and best_result.similarity >= confidence_threshold
    return RetrievalDecision(
        should_answer=should_answer,
        best_result=best_result,
        results=results,
        confidence_threshold=confidence_threshold,
    )
