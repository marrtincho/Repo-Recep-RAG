"""
Punto de entrada público de la capa de orchestration.

`ask` es la función que la interfaz (Streamlit) debería llamar: une
retrieval, la decisión de escalar/responder, generation cuando corresponde,
y el registro de métricas de cada interacción. Es el único módulo que la
interfaz necesita importar directamente.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import Settings
from src.generation.pipeline import GenerationClient, generate_answer
from src.generation.prompts import ESCALATION_MESSAGE
from src.orchestration.metrics import (
    RESULTADO_ACLARACION,
    RESULTADO_ESCALADA,
    RESULTADO_RESPONDIDA,
    log_interaction,
    record_feedback,
)
from src.retrieval.pipeline import retrieve
from src.retrieval.search import EmbeddingClient

VALID_MODES = ("directo", "explicado")


@dataclass(frozen=True)
class OrchestrationResult:
    """La respuesta final que ve el usuario, junto con lo necesario para registrar feedback después."""

    text: str
    mode: str
    sources: list[str]
    was_escalated: bool
    is_clarification: bool
    confidence: float
    interaction_id: str


def ask(
    query: str,
    mode: str,
    settings: Settings,
    embedding_client: EmbeddingClient,
    collection,
    generation_client: GenerationClient,
    history: list[tuple[str, str]] | None = None,
) -> OrchestrationResult:
    """
    Resuelve una pregunta de principio a fin: retrieval -> decisión -> generation (si aplica) -> métricas.

    Si la confianza no alcanza el umbral, NO se llama al modelo generador en
    absoluto (ver arquitectura en README.md): se devuelve ESCALATION_MESSAGE
    directamente, ahorrando una llamada innecesaria a Ollama.

    `history` se ignora: ni retrieval ni generation lo reciben, así que no
    se usa para enriquecer la búsqueda ni para preguntas de seguimiento. El
    modelo puede responder con una pregunta de aclaración en vez de una
    respuesta final (ver ADR 0010); esa rama se registra como una categoría
    de resultado distinta, ni "respondida" ni "escalada".
    """
    if mode not in VALID_MODES:
        raise ValueError(f"mode debe ser uno de {VALID_MODES}, recibido: {mode!r}")

    decision = retrieve(query, settings, embedding_client, collection)

    is_clarification = False
    if decision.should_answer:
        answer = generate_answer(query, mode, decision, generation_client, allow_clarification=settings.allow_clarification)
        text = answer.text
        sources = answer.sources
        is_clarification = answer.is_clarification
        resultado = RESULTADO_ACLARACION if is_clarification else RESULTADO_RESPONDIDA
    else:
        text = ESCALATION_MESSAGE
        sources = []
        resultado = RESULTADO_ESCALADA

    interaction_id = log_interaction(
        feedback_log_path=settings.feedback_log_path,
        gap_log_path=settings.gap_log_path,
        pregunta=query,
        resultado=resultado,
        confianza=decision.confidence,
        documentos_fuente=sources,
        modo=mode,
    )

    return OrchestrationResult(
        text=text,
        mode=mode,
        sources=sources,
        was_escalated=not decision.should_answer,
        is_clarification=is_clarification,
        confidence=decision.confidence,
        interaction_id=interaction_id,
    )


def submit_feedback(interaction_id: str, feedback: str, settings: Settings) -> None:
    """Registra el feedback (👍/👎) del usuario sobre una interacción ya resuelta por `ask`."""
    record_feedback(settings.feedback_log_path, interaction_id, feedback)
