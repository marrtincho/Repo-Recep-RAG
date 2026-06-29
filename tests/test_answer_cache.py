"""Tests unitarios del caché semántico de respuestas validadas."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.orchestration.answer_cache import (
    add_tentative,
    load_cache,
    lookup,
    record_cache_negative,
    record_cache_positive,
)

# Embeddings mínimos (2 dimensiones) para tests rápidos sin Ollama.
_EMB_A = [1.0, 0.0]   # "pregunta A"
_EMB_B = [0.0, 1.0]   # "pregunta B" — ortogonal a A, similitud coseno = 0
_EMB_A2 = [0.99, 0.14]  # casi idéntico a A, similitud coseno ~0.99


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    return tmp_path / "answer_cache.json"


class TestLookup:
    def test_empty_cache_returns_none(self, cache_path):
        result = lookup(_EMB_A, "directo", cache_path, threshold=0.85)
        assert result is None

    def test_inactive_entry_not_returned(self, cache_path):
        cid = add_tentative("pregunta", _EMB_A, "respuesta", [], "directo", cache_path)
        # tentativa → active=False
        result = lookup(_EMB_A, "directo", cache_path, threshold=0.85)
        assert result is None

    def test_active_entry_returned_on_high_similarity(self, cache_path):
        cid = add_tentative("pregunta", _EMB_A, "respuesta", ["a.md"], "directo", cache_path)
        record_cache_positive(cid, cache_path)

        result = lookup(_EMB_A, "directo", cache_path, threshold=0.85)
        assert result is not None
        assert result["answer"] == "respuesta"
        assert result["cache_id"] == cid

    def test_low_similarity_not_returned(self, cache_path):
        cid = add_tentative("pregunta A", _EMB_A, "respuesta A", [], "directo", cache_path)
        record_cache_positive(cid, cache_path)

        # _EMB_B es ortogonal a _EMB_A → similitud = 0
        result = lookup(_EMB_B, "directo", cache_path, threshold=0.85)
        assert result is None

    def test_mode_mismatch_not_returned(self, cache_path):
        cid = add_tentative("pregunta", _EMB_A, "respuesta", [], "directo", cache_path)
        record_cache_positive(cid, cache_path)

        result = lookup(_EMB_A, "explicado", cache_path, threshold=0.85)
        assert result is None

    def test_prefers_higher_ratio_on_tie(self, cache_path):
        cid1 = add_tentative("pregunta 1", _EMB_A, "respuesta 1", [], "directo", cache_path)
        record_cache_positive(cid1, cache_path)
        record_cache_negative(cid1, cache_path)  # ratio = 0.5 (1 positivo, 1 negativo → sigue activo? no: 1>=1 → desactivo)

        # En realidad 1 negativo >= 1 positivo → desactivado. Probemos con 2 positivos y 1 negativo:
        cid2 = add_tentative("pregunta 2", _EMB_A2, "respuesta 2", [], "directo", cache_path)
        record_cache_positive(cid2, cache_path)
        record_cache_positive(cid2, cache_path)
        record_cache_negative(cid2, cache_path)  # ratio = 2/3

        result = lookup(_EMB_A, "directo", cache_path, threshold=0.85)
        assert result is not None
        assert result["cache_id"] == cid2


class TestAddTentative:
    def test_creates_inactive_entry(self, cache_path):
        cid = add_tentative("pregunta", _EMB_A, "respuesta", ["a.md"], "directo", cache_path)
        entries = load_cache(cache_path)
        assert len(entries) == 1
        assert entries[0]["active"] is False
        assert entries[0]["cache_id"] == cid

    def test_no_duplicate_for_very_similar_active_entry(self, cache_path):
        cid1 = add_tentative("pregunta", _EMB_A, "respuesta", [], "directo", cache_path)
        record_cache_positive(cid1, cache_path)

        # _EMB_A2 tiene similitud ~0.99 con _EMB_A → supera merge_threshold (0.95) → devuelve cid1
        cid2 = add_tentative("pregunta reformulada", _EMB_A2, "otra respuesta", [], "directo", cache_path)
        assert cid2 == cid1
        assert len(load_cache(cache_path)) == 1

    def test_creates_new_entry_for_different_question(self, cache_path):
        cid1 = add_tentative("pregunta A", _EMB_A, "respuesta A", [], "directo", cache_path)
        record_cache_positive(cid1, cache_path)

        cid2 = add_tentative("pregunta B", _EMB_B, "respuesta B", [], "directo", cache_path)
        assert cid2 != cid1
        assert len(load_cache(cache_path)) == 2


class TestFeedback:
    def test_positive_activates_entry(self, cache_path):
        cid = add_tentative("pregunta", _EMB_A, "respuesta", [], "directo", cache_path)
        record_cache_positive(cid, cache_path)

        entries = load_cache(cache_path)
        assert entries[0]["active"] is True
        assert entries[0]["positive_votes"] == 1

    def test_negative_deactivates_when_votes_equal(self, cache_path):
        cid = add_tentative("pregunta", _EMB_A, "respuesta", [], "directo", cache_path)
        record_cache_positive(cid, cache_path)   # positivos=1, activo
        record_cache_negative(cid, cache_path)   # negativos=1 >= positivos=1 → desactivar

        entries = load_cache(cache_path)
        assert entries[0]["active"] is False
        assert entries[0]["negative_votes"] == 1

    def test_multiple_positives_resist_single_negative(self, cache_path):
        cid = add_tentative("pregunta", _EMB_A, "respuesta", [], "directo", cache_path)
        record_cache_positive(cid, cache_path)
        record_cache_positive(cid, cache_path)   # positivos=2
        record_cache_negative(cid, cache_path)   # negativos=1 < positivos=2 → sigue activo

        entries = load_cache(cache_path)
        assert entries[0]["active"] is True

    def test_unknown_cache_id_does_not_raise(self, cache_path):
        record_cache_positive("id-inexistente", cache_path)
        record_cache_negative("id-inexistente", cache_path)
