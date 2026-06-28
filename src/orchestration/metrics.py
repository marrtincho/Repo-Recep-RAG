"""
Persistencia de métricas: registro de cada interacción y de los huecos de documentación detectados.

Implementación basada en CSV (ver plan de acción, sección 6, y
docs/decisiones/0008-interaction-id-y-gap-log.md): para el volumen esperado
de un prototipo de uso interno, no hace falta una base de datos.
"""

from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

FEEDBACK_LOG_COLUMNS = [
    "interaction_id",
    "timestamp",
    "pregunta",
    "resultado",
    "confianza",
    "documentos_fuente",
    "modo",
    "cache_id",
    "feedback",
]
GAP_LOG_COLUMNS = ["timestamp", "pregunta", "modo", "confianza_mejor_resultado"]

FEEDBACK_SIN_EVALUAR = "sin_evaluar"
FEEDBACK_CORRECTO = "correcto"
FEEDBACK_INCORRECTO = "incorrecto"
RESULTADO_RESPONDIDA = "respondida"
RESULTADO_ESCALADA = "escalada"
RESULTADO_ACLARACION = "aclaracion"
RESULTADOS_VALIDOS = (RESULTADO_RESPONDIDA, RESULTADO_ESCALADA, RESULTADO_ACLARACION)


def _read_or_create(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.DataFrame(columns=columns)


def _write(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _append_row(path: Path, row: dict, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def log_interaction(
    feedback_log_path: Path,
    gap_log_path: Path,
    pregunta: str,
    resultado: str,
    confianza: float,
    documentos_fuente: list[str],
    modo: str,
    cache_id: str | None = None,
) -> str:
    """
    Registra una interacción en feedback_log.csv y, si fue escalada, también en gap_log.csv.

    Returns:
        El interaction_id generado. La interfaz debe guardarlo para poder
        asociarle feedback (👍/👎) más adelante con `record_feedback`.
    """
    if resultado not in RESULTADOS_VALIDOS:
        raise ValueError(f"resultado debe ser uno de {RESULTADOS_VALIDOS}, recibido: {resultado!r}")

    interaction_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    _append_row(
        feedback_log_path,
        {
            "interaction_id": interaction_id,
            "timestamp": timestamp,
            "pregunta": pregunta,
            "resultado": resultado,
            "confianza": f"{confianza:.4f}",
            "documentos_fuente": ";".join(documentos_fuente),
            "modo": modo,
            "cache_id": cache_id or "",
            "feedback": FEEDBACK_SIN_EVALUAR,
        },
        FEEDBACK_LOG_COLUMNS,
    )

    if resultado == RESULTADO_ESCALADA:
        _append_row(
            gap_log_path,
            {
                "timestamp": timestamp,
                "pregunta": pregunta,
                "modo": modo,
                "confianza_mejor_resultado": f"{confianza:.4f}",
            },
            GAP_LOG_COLUMNS,
        )

    return interaction_id


def record_feedback(feedback_log_path: Path, interaction_id: str, feedback: str) -> str | None:
    """
    Actualiza el campo feedback de una interacción ya registrada (👍/👎 desde la interfaz).

    Lanza ValueError si el interaction_id no existe — más seguro que fallar
    en silencio si la interfaz manda un id incorrecto o de un log ya rotado
    (ver docs/decisiones/0008).

    Returns:
        El cache_id asociado a la interacción, o None si no tiene entrada de caché.
        Lo usa submit_feedback() en orchestration/pipeline.py para actualizar el
        caché semántico con el feedback del usuario.
    """
    if feedback not in (FEEDBACK_CORRECTO, FEEDBACK_INCORRECTO):
        raise ValueError(f"feedback debe ser '{FEEDBACK_CORRECTO}' o '{FEEDBACK_INCORRECTO}', recibido: {feedback!r}")

    df = _read_or_create(feedback_log_path, FEEDBACK_LOG_COLUMNS)
    mask = df["interaction_id"] == interaction_id
    if not mask.any():
        raise ValueError(f"No se encontró ninguna interacción con id {interaction_id!r} en {feedback_log_path}")

    cache_id = df.loc[mask, "cache_id"].iloc[0] if "cache_id" in df.columns else ""
    df.loc[mask, "feedback"] = feedback
    _write(feedback_log_path, df)
    return cache_id or None


def compute_summary_metrics(feedback_log_path: Path) -> dict[str, float | int]:
    """
    Calcula las métricas agregadas del plan de acción (sección 6): tasa de
    respuesta, tasa de escalado y tasa de acierto.

    Devuelve proporciones en [0, 1], no porcentajes formateados — el
    panel de métricas de Streamlit decide cómo mostrarlas.
    """
    df = _read_or_create(feedback_log_path, FEEDBACK_LOG_COLUMNS)
    total = len(df)
    if total == 0:
        return {
            "total_interacciones": 0,
            "tasa_respuesta": 0.0,
            "tasa_escalado": 0.0,
            "tasa_aclaracion": 0.0,
            "tasa_acierto": 0.0,
        }

    respondidas = int((df["resultado"] == RESULTADO_RESPONDIDA).sum())
    escaladas = int((df["resultado"] == RESULTADO_ESCALADA).sum())
    aclaraciones = int((df["resultado"] == RESULTADO_ACLARACION).sum())
    evaluadas = df[df["feedback"] != FEEDBACK_SIN_EVALUAR]
    aciertos = int((evaluadas["feedback"] == FEEDBACK_CORRECTO).sum())

    return {
        "total_interacciones": total,
        "tasa_respuesta": respondidas / total,
        "tasa_escalado": escaladas / total,
        "tasa_aclaracion": aclaraciones / total,
        "tasa_acierto": (aciertos / len(evaluadas)) if len(evaluadas) > 0 else 0.0,
    }


def get_frequent_questions(
    feedback_log_path: Path,
    top_n: int = 5,
    min_count: int = 2,
) -> list[str]:
    """
    Devuelve las preguntas respondidas más frecuentes del log.

    Solo incluye preguntas con resultado "respondida" (no escaladas ni
    aclaraciones) y que hayan aparecido al menos `min_count` veces — evita
    mostrar como "frecuente" algo que solo preguntó una persona una vez.
    Las preguntas se normalizan a minúsculas para que "Cómo cargo parking"
    y "como cargo parking" cuenten como la misma.

    Devuelve lista vacía si no hay suficientes datos: la UI simplemente no
    muestra la sección en ese caso.
    """
    df = _read_or_create(feedback_log_path, FEEDBACK_LOG_COLUMNS)
    if df.empty:
        return []

    respondidas = df[df["resultado"] == RESULTADO_RESPONDIDA]["pregunta"]
    if respondidas.empty:
        return []

    counts = respondidas.str.lower().str.strip().value_counts()
    frecuentes = counts[counts >= min_count].head(top_n)

    # Texto original (no normalizado) de la primera aparición de cada pregunta frecuente.
    respondidas_df = df[df["resultado"] == RESULTADO_RESPONDIDA].copy()
    respondidas_df["_norm"] = respondidas_df["pregunta"].str.lower().str.strip()
    first_text = respondidas_df.drop_duplicates("_norm").set_index("_norm")["pregunta"]
    return [first_text[norm].strip() for norm in frecuentes.index if norm in first_text]