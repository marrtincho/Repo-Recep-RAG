"""
Punto de entrada público de la capa de retrieval.

`retrieve` es la única función que orchestration (y, más adelante,
generation) debería necesitar llamar: une búsqueda semántica, contextualización
con historial conversacional (ver ADR 0010) y evaluación contra el umbral de
confianza en una sola llamada. Ya no filtra por modo directo/explicado (ver
ADR 0011, reversión explícita de ADR 0007).
"""

from __future__ import annotations

from src.config import Settings
from src.retrieval.confidence import RetrievalDecision, evaluate
from src.retrieval.search import EmbeddingClient, search


def _contextualize_query(query: str, history: list[tuple[str, str]] | None, max_turns: int) -> str:
    """
    Combina la consulta actual con los últimos turnos de conversación para retrieval.

    Una pregunta de seguimiento como "¿y si se niega?" Apenas tiene señal
    semántica por sí sola — sin el turno anterior, el retrieval no tiene
    forma de saber que sigue hablando de un overbooking. Se usa
    concatenación simple (no una llamada extra a Ollama para reescribir la
    consulta) — ver ADR 0010 para el porqué de esa decisión.
    """
    if not history:
        return query
    recent = history[-(max_turns * 2):]
    parts = [content for _, content in recent] + [query]
    return " ".join(parts)


def retrieve(
    query: str,
    settings: Settings,
    embedding_client: EmbeddingClient,
    collection,
    history: list[tuple[str, str]] | None = None,
    precomputed_embedding: list[float] | None = None,
) -> RetrievalDecision:
    """
    Busca `query` en `collection` y decide si hay confianza suficiente para responder.

    Ya NO filtra por modo (ver docs/decisiones/0011, reversión explícita de
    0007): el retrieval trae lo más relevante sin importar si el chunk es
    "Resumen rápido" o "Procedimiento detallado" — el modo solo controla
    cómo se redacta la respuesta en la capa de generation, nunca qué
    información puede ver el modelo. Si `history` se indica, la consulta de
    búsqueda se enriquece con los turnos previos (ver docs/decisiones/0010)
    para que las preguntas de seguimiento recuperen bien aunque por sí solas
    sean ambiguas.
    """
    search_query = _contextualize_query(query, history, settings.max_history_turns)

    # Excluir chunks de "Preguntas habituales relacionadas": esa subsección existe para
    # mejorar la similitud semántica en el índice, pero no contiene respuestas — si llega
    # al contexto del modelo, ocupa espacio sin aportar información útil y puede desplazar
    # chunks con el contenido real.
    where = {"subseccion": {"$ne": "Preguntas habituales relacionadas"}}

    results = search(
        query=search_query,
        embedding_client=embedding_client,
        collection=collection,
        top_k=settings.top_k,
        where=where,
        precomputed_embedding=precomputed_embedding,
    )
    return evaluate(results, confidence_threshold=settings.confidence_threshold)