"""
Plantillas de prompt para el modelo generador.

Dos modos (ver ADR 0003): "directo" pide una síntesis breve y accionable;
"explicado" pide contexto y razonamiento completos. El modo solo controla
CÓMO se redacta la respuesta — ya no qué información puede ver el modelo:
el retrieval trae lo más relevante sin filtrar por modo (ver ADR 0011,
reversión explícita de ADR 0007). Ambos modos comparten la misma
instrucción de seguridad — la capa 2 (a nivel de prompt) del mecanismo de
escalado de dos capas. La capa 1 (el umbral de confianza, ya evaluado antes
de llegar aquí) decidió que hay suficiente similitud textual para intentar
responder, pero similitud textual no garantiza que el fragmento recuperado
conteste realmente la pregunta concreta — de ahí que el modelo deba poder
negarse a responder incluso habiendo pasado el umbral.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.retrieval.search import SearchResult

ESCALATION_MESSAGE = "No tengo información suficiente sobre esto, consulta con tu responsable."
CLARIFICATION_PREFIX = "ACLARACIÓN:"

_CORE_INSTRUCTION = (
    "Tu trabajo es ayudar al personal de recepción respondiendo su pregunta "
    "a partir del CONTEXTO que se te da más abajo. El contexto son extractos "
    "de los manuales internos del hotel. Lee todos los extractos, identifica "
    "los que tratan sobre la pregunta, y explica la respuesta con tus propias "
    "palabras, de forma clara y natural, como un compañero con experiencia se "
    "lo explicaría a otro. No hace falta que uses todos los extractos: usa los "
    "que de verdad responden la pregunta e ignora los que no vienen al caso."
)

_SAFETY_INSTRUCTION = (
    "Responde SOLO con lo que diga el contexto. No añadas conocimiento general "
    "tuyo ni completes con lo que suele ser habitual en otros hoteles: si un "
    "dato no está escrito en los extractos, no lo menciones. NUNCA inventes "
    "nombres de documentos ni cites fuentes que no aparezcan literalmente en "
    "los extractos que recibes — si no ves el nombre del archivo en el contexto, "
    "no lo pongas. La fuente que cites al final debe ser exactamente el nombre "
    "de archivo que aparece en el extracto que usaste, copiado tal cual. Si "
    "NINGUNO de los extractos trata sobre lo que se pregunta, entonces — y "
    f'solo entonces — responde exactamente: "{ESCALATION_MESSAGE}"'
)

_CLARIFICATION_INSTRUCTION = (
    "Si el contexto responde la pregunta pero hay un dato puntual de la "
    "situación que cambiaría qué hacer, puedes pedirlo respondiendo solo con "
    f'"{CLARIFICATION_PREFIX}" y una pregunta breve. No vuelvas a preguntar '
    "algo que el usuario ya respondió antes en la conversación."
)

_MODE_INSTRUCTIONS = {
    "directo": (
        "Responde en 2-4 frases, directo a la acción concreta a realizar."
    ),
    "explicado": (
        "Responde explicando tanto qué hacer como por qué; puedes extenderte "
        "si ayuda a entenderlo."
    ),
}

DEFAULT_MODE = "explicado"


@lru_cache(maxsize=4)
def build_system_prompt(mode: str, allow_clarification: bool = False) -> str:
    """Construye el system prompt para el modo dado ('directo' o 'explicado').

    Si allow_clarification es False (por defecto), se omite la instrucción de
    aclaración por completo: el modelo siempre responde con lo que tiene o
    escala, nunca pide datos. Los modelos pequeños tienden a abusar de las
    aclaraciones (pedir datos que no necesitan, entrar en bucle), así que se
    desactiva salvo que se active explícitamente en settings.yaml.
    """
    mode_instruction = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS[DEFAULT_MODE])
    clarification_block = f"{_CLARIFICATION_INSTRUCTION}\n\n" if allow_clarification else ""
    return (
        "Eres el asistente operativo interno de recepción de un hotel.\n\n"
        f"{_CORE_INSTRUCTION}\n\n"
        f"{mode_instruction}\n\n"
        f"{_SAFETY_INSTRUCTION}\n\n"
        f"{clarification_block}"
        "Al final de una respuesta basada en el contexto, indica la fuente "
        "entre paréntesis, p. ej. (fuente: Deducciones y Abonos.md)."
    )


def build_context_block(results: list[SearchResult]) -> str:
    """Construye el bloque de contexto a partir de los chunks recuperados, numerados para poder citarlos."""
    if not results:
        return "(sin contexto disponible)"
    blocks = []
    for index, result in enumerate(results, start=1):
        source_path = result.metadata.get("source_path", "")
        source_name = Path(source_path).name if source_path else "fuente desconocida"
        blocks.append(f"[{index}] (fuente: {source_name})\n{result.text}")
    return "\n\n".join(blocks)


def build_history_block(history: list[tuple[str, str]] | None) -> str:
    """
    Construye el bloque de conversación previa para el prompt.

    Deja explícito que el historial es solo para entender de qué se está
    hablando (referentes como "ese huésped", "y si se niega"), nunca una
    fuente de hechos: los hechos siguen viniendo exclusivamente del CONTEXTO.
    Sin esa aclaración, el modelo podría tratar su propia respuesta anterior
    como si fuera información verificada, debilitando la garantía de no
    inventar datos.
    """
    if not history:
        return ""
    lines = [f"{'Personal' if role == 'user' else 'Asistente'}: {content}" for role, content in history]
    return (
        "CONVERSACIÓN PREVIA (solo para entender de qué se habla; los HECHOS "
        "deben venir únicamente del CONTEXTO de abajo, nunca de lo que dijiste "
        "antes):\n" + "\n".join(lines)
    )


def build_user_prompt(query: str, results: list[SearchResult], history: list[tuple[str, str]] | None = None) -> str:
    """Construye el mensaje de usuario final: historial (si lo hay) + contexto + la pregunta actual."""
    context = build_context_block(results)
    history_block = build_history_block(history)
    prefix = f"{history_block}\n\n" if history_block else ""
    return f"{prefix}CONTEXTO:\n{context}\n\nPREGUNTA ACTUAL: {query}"