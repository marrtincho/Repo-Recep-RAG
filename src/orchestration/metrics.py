"""
Persistencia de métricas: registro de cada interacción y de los huecos de documentación detectados.

Implementación basada en CSV (ver plan de acción, sección 6, y
docs/decisiones/0008-interaction-id-y-gap-log.md): para el volumen esperado
de un prototipo de uso interno, no hace falta una base de datos.
"""

from __future__ import annotations

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


def log_interaction(
    feedback_log_path: Path,
    gap_log_path: Path,
    pregunta: str,
    resultado: str,
    confianza: float,
    documentos_fuente: list[str],
    modo: str,
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

    df = _read_or_create(feedback_log_path, FEEDBACK_LOG_COLUMNS)
    new_row = pd.DataFrame(
        [
            {
                "interaction_id": interaction_id,
                "timestamp": timestamp,
                "pregunta": pregunta,
                "resultado": resultado,
                "confianza": f"{confianza:.4f}",
                "documentos_fuente": ";".join(documentos_fuente),
                "modo": modo,
                "feedback": FEEDBACK_SIN_EVALUAR,
            }
        ]
    )
    df = pd.concat([df, new_row], ignore_index=True)
    _write(feedback_log_path, df)

    if resultado == RESULTADO_ESCALADA:
        gap_df = _read_or_create(gap_log_path, GAP_LOG_COLUMNS)
        gap_row = pd.DataFrame(
            [
                {
                    "timestamp": timestamp,
                    "pregunta": pregunta,
                    "modo": modo,
                    "confianza_mejor_resultado": f"{confianza:.4f}",
                }
            ]
        )
        gap_df = pd.concat([gap_df, gap_row], ignore_index=True)
        _write(gap_log_path, gap_df)

    return interaction_id


def record_feedback(feedback_log_path: Path, interaction_id: str, feedback: str) -> None:
    """
    Actualiza el campo feedback de una interacción ya registrada (👍/👎 desde la interfaz).

    Lanza ValueError si el interaction_id no existe — más seguro que fallar
    en silencio si la interfaz manda un id incorrecto o de un log ya rotado
    (ver docs/decisiones/0008).
    """
    if feedback not in (FEEDBACK_CORRECTO, FEEDBACK_INCORRECTO):
        raise ValueError(f"feedback debe ser '{FEEDBACK_CORRECTO}' o '{FEEDBACK_INCORRECTO}', recibido: {feedback!r}")

    df = _read_or_create(feedback_log_path, FEEDBACK_LOG_COLUMNS)
    mask = df["interaction_id"] == interaction_id
    if not mask.any():
        raise ValueError(f"No se encontró ninguna interacción con id {interaction_id!r} en {feedback_log_path}")

    df.loc[mask, "feedback"] = feedback
    _write(feedback_log_path, df)


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
