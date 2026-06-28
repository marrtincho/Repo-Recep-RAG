"""
Punto de entrada público de la capa de orchestration.

`ask` es la función que la interfaz (Streamlit) debería llamar: une
retrieval, la decisión de escalar/responder, generation cuando corresponde,
y el registro de métricas de cada interacción. Es el único módulo que la
interfaz necesita importar directamente.

Caché semántico: antes de invocar el pipeline completo (retrieval + LLM),
`ask` busca en el caché de respuestas validadas con 👍. Un cache hit evita
ambas llamadas costosas y devuelve la respuesta validada directamente. El
embedding de la consulta se computa una sola vez y se reutiliza tanto para
el lookup del caché como para el retrieval en caso de miss.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import Settings
from src.generation.pipeline import GenerationClient, generate_answer
from src.generation.prompts import ESCALATION_MESSAGE
from src.orchestration.answer_cache import (
    add_tentative,
    lookup,
    record_cache_negative,
    record_cache_positive,
)
from src.orchestration.metrics import (
    FEEDBACK_CORRECTO,
    FEEDBACK_INCORRECTO,
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
    cache_id: str | None = None
    was_cached: bool = False


def ask(
    query: str,
    mode: str,
    settings: Settings,
    embedding_client: EmbeddingClient,
    collection,
    generation_client: GenerationClient,
    history: list[tuple[str, str]] | None = None,
    use_cache: bool = True,
) -> OrchestrationResult:
    """
    Resuelve una pregunta de principio a fin.

    Flujo con caché semántico activo (use_cache=True):
      1. Embebe la consulta (una sola vez, se reutiliza en retrieval si hay miss).
      2. Busca en el caché de respuestas validadas (👍). Si hay hit con
         similitud >= semantic_cache_similarity_threshold, devuelve la respuesta
         sin llamar a ChromaDB ni al LLM generador.
      3. En cache miss: retrieve → generate → crea entrada tentativa en caché.
         El feedback posterior activará (👍) o rechazará (👎) esa entrada.

    Si use_cache=False o la colección no tiene caché habilitado, se ejecuta
    el pipeline completo directamente.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"mode debe ser uno de {VALID_MODES}, recibido: {mode!r}")

    # Embeber la consulta una sola vez — se usa para cache lookup y para retrieval.
    # Se usa la misma contextualización de historial que hace retrieve() internamente,
    # para que el embedding del caché y el de búsqueda sean siempre el mismo vector.
    if history:
        recent = history[-(settings.max_history_turns * 2):]
        embed_query = " ".join(content for _, content in recent) + " " + query
    else:
        embed_query = query
    [query_embedding] = embedding_client.embed_batch([embed_query])

    # ── Caché semántico ───────────────────────────────────────────────────────
    if use_cache:
        cache_hit = lookup(
            query_embedding=query_embedding,
            mode=mode,
            path=settings.semantic_cache_path,
            threshold=settings.semantic_cache_similarity_threshold,
        )
        if cache_hit:
            interaction_id = log_interaction(
                feedback_log_path=settings.feedback_log_path,
                gap_log_path=settings.gap_log_path,
                pregunta=query,
                resultado=RESULTADO_RESPONDIDA,
                confianza=1.0,
                documentos_fuente=cache_hit["sources"],
                modo=mode,
                cache_id=cache_hit["cache_id"],
            )
            return OrchestrationResult(
                text=cache_hit["answer"],
                mode=mode,
                sources=cache_hit["sources"],
                was_escalated=False,
                is_clarification=False,
                confidence=1.0,
                interaction_id=interaction_id,
                cache_id=cache_hit["cache_id"],
                was_cached=True,
            )

    # ── Pipeline completo (cache miss o caché desactivado) ────────────────────
    decision = retrieve(
        query, settings, embedding_client, collection,
        history=history,
        precomputed_embedding=query_embedding,
    )

    is_clarification = False
    if decision.should_answer:
        answer = generate_answer(query, mode, decision, generation_client, history=history, allow_clarification=settings.allow_clarification)
        text = answer.text
        sources = answer.sources
        is_clarification = answer.is_clarification
        resultado = RESULTADO_ACLARACION if is_clarification else RESULTADO_RESPONDIDA
    else:
        text = ESCALATION_MESSAGE
        sources = []
        resultado = RESULTADO_ESCALADA

    # Crear entrada tentativa en caché para respuestas respondidas (no escaladas ni aclaraciones).
    cache_id: str | None = None
    if resultado == RESULTADO_RESPONDIDA:
        cache_id = add_tentative(
            query_text=query,
            query_embedding=query_embedding,
            answer=text,
            sources=sources,
            mode=mode,
            path=settings.semantic_cache_path,
        )

    interaction_id = log_interaction(
        feedback_log_path=settings.feedback_log_path,
        gap_log_path=settings.gap_log_path,
        pregunta=query,
        resultado=resultado,
        confianza=decision.confidence,
        documentos_fuente=sources,
        modo=mode,
        cache_id=cache_id,
    )

    return OrchestrationResult(
        text=text,
        mode=mode,
        sources=sources,
        was_escalated=not decision.should_answer,
        is_clarification=is_clarification,
        confidence=decision.confidence,
        interaction_id=interaction_id,
        cache_id=cache_id,
        was_cached=False,
    )


def submit_feedback(interaction_id: str, feedback: str, settings: Settings) -> None:
    """
    Registra el feedback (👍/👎) del usuario y actualiza el caché semántico.

    record_feedback actualiza el CSV y devuelve el cache_id de la interacción.
    Con ese id se activa (👍) o se penaliza (👎) la entrada correspondiente.
    """
    cache_id = record_feedback(settings.feedback_log_path, interaction_id, feedback)
    if cache_id:
        if feedback == FEEDBACK_CORRECTO:
            record_cache_positive(cache_id, settings.semantic_cache_path)
        elif feedback == FEEDBACK_INCORRECTO:
            record_cache_negative(cache_id, settings.semantic_cache_path)
