"""Tests de src/orchestration/metrics.py — CSVs reales en tmp_path, sin mocks (es lógica de archivo puro)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.orchestration.metrics import (
    RESULTADO_ACLARACION,
    RESULTADO_ESCALADA,
    RESULTADO_RESPONDIDA,
    compute_summary_metrics,
    log_interaction,
    record_feedback,
)


@pytest.fixture
def paths(tmp_path):
    return {"feedback": tmp_path / "metrics" / "feedback_log.csv", "gap": tmp_path / "metrics" / "gap_log.csv"}


class TestLogInteraction:
    def test_creates_feedback_log_with_one_row(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "¿pregunta?", RESULTADO_RESPONDIDA, 0.9, ["a.md"], "directo")
        df = pd.read_csv(paths["feedback"], dtype=str)
        assert len(df) == 1
        assert df.iloc[0]["pregunta"] == "¿pregunta?"
        assert df.iloc[0]["resultado"] == RESULTADO_RESPONDIDA
        assert df.iloc[0]["modo"] == "directo"
        assert df.iloc[0]["documentos_fuente"] == "a.md"

    def test_returns_unique_interaction_id_each_call(self, paths):
        id1 = log_interaction(paths["feedback"], paths["gap"], "p1", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        id2 = log_interaction(paths["feedback"], paths["gap"], "p2", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        assert id1 != id2

    def test_new_interaction_starts_with_feedback_sin_evaluar(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "p", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        df = pd.read_csv(paths["feedback"], dtype=str)
        assert df.iloc[0]["feedback"] == "sin_evaluar"

    def test_multiple_sources_joined_with_semicolon(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "p", RESULTADO_RESPONDIDA, 0.9, ["a.md", "b.md"], "directo")
        df = pd.read_csv(paths["feedback"], dtype=str)
        assert df.iloc[0]["documentos_fuente"] == "a.md;b.md"

    def test_escalated_interaction_also_written_to_gap_log(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "pregunta sin respuesta", RESULTADO_ESCALADA, 0.3, [], "explicado")
        gap_df = pd.read_csv(paths["gap"], dtype=str)
        assert len(gap_df) == 1
        assert gap_df.iloc[0]["pregunta"] == "pregunta sin respuesta"

    def test_answered_interaction_not_written_to_gap_log(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "p", RESULTADO_RESPONDIDA, 0.9, ["a.md"], "directo")
        assert not paths["gap"].exists()

    def test_appends_to_existing_log_without_overwriting(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "p1", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        log_interaction(paths["feedback"], paths["gap"], "p2", RESULTADO_RESPONDIDA, 0.8, [], "explicado")
        df = pd.read_csv(paths["feedback"], dtype=str)
        assert len(df) == 2
        assert list(df["pregunta"]) == ["p1", "p2"]

    def test_invalid_resultado_raises_value_error(self, paths):
        with pytest.raises(ValueError, match="resultado"):
            log_interaction(paths["feedback"], paths["gap"], "p", "estado-invalido", 0.9, [], "directo")


class TestRecordFeedback:
    def test_updates_feedback_field_of_correct_row(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "p1", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        interaction_id = log_interaction(paths["feedback"], paths["gap"], "p2", RESULTADO_RESPONDIDA, 0.8, [], "directo")

        record_feedback(paths["feedback"], interaction_id, "correcto")

        df = pd.read_csv(paths["feedback"], dtype=str)
        row = df[df["interaction_id"] == interaction_id].iloc[0]
        assert row["feedback"] == "correcto"
        # La otra fila no debe verse afectada
        other_row = df[df["pregunta"] == "p1"].iloc[0]
        assert other_row["feedback"] == "sin_evaluar"

    def test_unknown_interaction_id_raises_value_error(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "p", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        with pytest.raises(ValueError, match="no se encontró|No se encontró"):
            record_feedback(paths["feedback"], "id-que-no-existe", "correcto")

    def test_invalid_feedback_value_raises_value_error(self, paths):
        interaction_id = log_interaction(paths["feedback"], paths["gap"], "p", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        with pytest.raises(ValueError, match="feedback"):
            record_feedback(paths["feedback"], interaction_id, "mas-o-menos")


class TestComputeSummaryMetrics:
    def test_empty_log_returns_zeros(self, paths):
        metrics = compute_summary_metrics(paths["feedback"])
        assert metrics == {
            "total_interacciones": 0,
            "tasa_respuesta": 0.0,
            "tasa_escalado": 0.0,
            "tasa_aclaracion": 0.0,
            "tasa_acierto": 0.0,
        }

    def test_tasa_aclaracion_counted_separately(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "p1", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        log_interaction(paths["feedback"], paths["gap"], "p2", RESULTADO_ACLARACION, 0.5, [], "directo")
        log_interaction(paths["feedback"], paths["gap"], "p3", RESULTADO_ESCALADA, 0.2, [], "directo")

        metrics = compute_summary_metrics(paths["feedback"])

        assert metrics["total_interacciones"] == 3
        assert metrics["tasa_respuesta"] == pytest.approx(1 / 3)
        assert metrics["tasa_aclaracion"] == pytest.approx(1 / 3)
        assert metrics["tasa_escalado"] == pytest.approx(1 / 3)

    def test_clarification_not_written_to_gap_log(self, paths):
        """Una aclaración no es un hueco de documentación: es parte normal del flujo."""
        log_interaction(paths["feedback"], paths["gap"], "p", RESULTADO_ACLARACION, 0.5, [], "directo")
        assert not paths["gap"].exists()

    def test_tasa_respuesta_and_escalado(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "p1", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        log_interaction(paths["feedback"], paths["gap"], "p2", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        log_interaction(paths["feedback"], paths["gap"], "p3", RESULTADO_ESCALADA, 0.2, [], "directo")

        metrics = compute_summary_metrics(paths["feedback"])

        assert metrics["total_interacciones"] == 3
        assert metrics["tasa_respuesta"] == pytest.approx(2 / 3)
        assert metrics["tasa_escalado"] == pytest.approx(1 / 3)

    def test_tasa_acierto_only_counts_evaluated_interactions(self, paths):
        id1 = log_interaction(paths["feedback"], paths["gap"], "p1", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        id2 = log_interaction(paths["feedback"], paths["gap"], "p2", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        log_interaction(paths["feedback"], paths["gap"], "p3", RESULTADO_RESPONDIDA, 0.9, [], "directo")  # sin evaluar
        record_feedback(paths["feedback"], id1, "correcto")
        record_feedback(paths["feedback"], id2, "incorrecto")

        metrics = compute_summary_metrics(paths["feedback"])

        assert metrics["tasa_acierto"] == pytest.approx(0.5)  # 1 de 2 evaluadas, la tercera no cuenta

    def test_tasa_acierto_zero_when_nothing_evaluated_yet(self, paths):
        log_interaction(paths["feedback"], paths["gap"], "p1", RESULTADO_RESPONDIDA, 0.9, [], "directo")
        metrics = compute_summary_metrics(paths["feedback"])
        assert metrics["tasa_acierto"] == 0.0
