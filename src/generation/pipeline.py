"""
Punto de entrada público de la capa de generación.

`generate_answer` asume que la decisión de responder (en vez de escalar) ya
se tomó en la capa de retrieval (`RetrievalDecision.should_answer`). Esta
función no vuelve a evaluarla: es responsabilidad de orchestration decidir
si llamar aquí o devolver directamente `ESCALATION_MESSAGE` sin generar nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.generation.prompts import CLARIFICATION_PREFIX, build_system_prompt, build_user_prompt
from src.retrieval.confidence import RetrievalDecision
from src.retrieval.search import SearchResult


class GenerationClient(Protocol):
    """Contrato mínimo que esta capa necesita de un cliente de generación."""

    def generate(self, system_prompt: str, user_prompt: str) -> str: ...


@dataclass(frozen=True)
class GeneratedAnswer:
    """La respuesta final generada, junto con el modo usado, las fuentes citables y si es una aclaración."""

    text: str
    mode: str
    sources: list[str]
    is_clarification: bool = False


def select_context(decision: RetrievalDecision) -> list[SearchResult]:
    """
    Filtra los resultados de retrieval a los que cumplen el umbral de confianza.

    `decision.results` puede incluir hasta `top_k` resultados, algunos por
    debajo del umbral (solo estaban ahí por no haber nada mejor). Pasarle
    esos al modelo como "contexto" sería darle ruido de baja relevancia, así
    que solo se incluyen los que individualmente superan el umbral.
    """
    return [r for r in decision.results if r.similarity >= decision.confidence_threshold]


def generate_answer(
    query: str,
    mode: str,
    decision: RetrievalDecision,
    generation_client: GenerationClient,
    history: list[tuple[str, str]] | None = None,
    allow_clarification: bool = False,
) -> GeneratedAnswer:
    """Genera la respuesta final a partir de una RetrievalDecision ya evaluada como should_answer=True."""
    if not decision.should_answer:
        raise ValueError(
            "generate_answer no debería llamarse cuando should_answer es False; "
            "usa ESCALATION_MESSAGE de src.generation.prompts directamente."
        )

    context_results = select_context(decision)
    system_prompt = build_system_prompt(mode, allow_clarification=allow_clarification)
    user_prompt = build_user_prompt(query, context_results, history=history)

    raw_text = generation_client.generate(system_prompt, user_prompt)
    is_clarification, text = _split_clarification(raw_text)

    sources = (
        []
        if is_clarification
        else sorted(
            {
                Path(r.metadata["source_path"]).name
                for r in context_results
                if r.metadata.get("source_path")
            }
        )
    )

    return GeneratedAnswer(text=text, mode=mode, sources=sources, is_clarification=is_clarification)


def _split_clarification(raw_text: str) -> tuple[bool, str]:
    """
    Detecta si la respuesta del modelo es una pregunta de aclaración (ver ADR 0010).

    Si el texto empieza con CLARIFICATION_PREFIX (sin distinguir mayúsculas,
    por si el modelo no respeta el caso exacto), se considera aclaración y se
    devuelve sin el prefijo. Si no, se trata como respuesta normal tal cual.
    """
    stripped = raw_text.strip()
    if stripped.upper().startswith(CLARIFICATION_PREFIX.upper()):
        return True, stripped[len(CLARIFICATION_PREFIX) :].strip()
    return False, stripped
