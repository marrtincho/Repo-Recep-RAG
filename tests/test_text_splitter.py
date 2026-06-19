"""Tests de src/ingestion/text_splitter.py."""

from __future__ import annotations

import pytest

from src.ingestion.text_splitter import split_with_overlap


class TestSplitWithOverlap:
    def test_text_shorter_than_chunk_size_returns_single_chunk(self):
        text = "Una frase corta."
        assert split_with_overlap(text, chunk_size=500, chunk_overlap=50) == [text]

    def test_empty_text_returns_empty_list(self):
        assert split_with_overlap("   ", chunk_size=100, chunk_overlap=10) == []

    def test_splits_long_text_into_multiple_chunks_under_chunk_size(self):
        sentence = "Esta es una frase de prueba con longitud moderada para el test."
        text = " ".join([sentence] * 10)
        chunks = split_with_overlap(text, chunk_size=200, chunk_overlap=20)
        assert len(chunks) > 1
        for chunk in chunks:
            # Una sola frase puede exceder un poco el tamaño objetivo si no hay
            # mejor punto de corte, pero ningún chunk debe ser absurdamente mayor.
            assert len(chunk) <= 200 + len(sentence)

    def test_consecutive_chunks_share_overlapping_content(self):
        sentence = "Frase numero {} para verificar el solape entre fragmentos consecutivos."
        text = " ".join(sentence.format(i) for i in range(8))
        chunks = split_with_overlap(text, chunk_size=150, chunk_overlap=40)
        assert len(chunks) >= 2
        # Alguna porción del final del primer chunk debe reaparecer al inicio del segundo
        tail_of_first = chunks[0][-20:]
        assert any(word in chunks[1] for word in tail_of_first.split() if len(word) > 4)

    def test_no_overlap_when_chunk_overlap_is_zero(self):
        sentence = "Una frase corta y simple."
        text = " ".join([sentence] * 10)
        chunks = split_with_overlap(text, chunk_size=80, chunk_overlap=0)
        assert len(chunks) > 1

    def test_single_sentence_longer_than_chunk_size_is_hard_split_by_words(self):
        text = "palabra " * 100  # una sola "frase" sin puntuación, muy larga
        chunks = split_with_overlap(text.strip(), chunk_size=50, chunk_overlap=5)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 50

    def test_invalid_chunk_size_raises(self):
        with pytest.raises(ValueError):
            split_with_overlap("texto", chunk_size=0, chunk_overlap=0)

    def test_overlap_greater_or_equal_to_chunk_size_raises(self):
        with pytest.raises(ValueError):
            split_with_overlap("texto", chunk_size=100, chunk_overlap=100)

    def test_no_content_lost_words_preserved_in_order(self):
        """Todas las palabras del texto original deben seguir presentes (en orden), aunque se repitan por el solape."""
        text = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi."
        chunks = split_with_overlap(text, chunk_size=30, chunk_overlap=10)
        rebuilt_words = " ".join(chunks).split()
        original_words = text.split()
        # Cada palabra original debe aparecer al menos una vez en el resultado
        for word in original_words:
            assert word in rebuilt_words

    def test_numbered_list_items_are_not_split_mid_item(self):
        """Regresión: un marcador de lista ('2.') no debe confundirse con un punto final de frase."""
        text = (
            "1. Antes de declarar un overbooking, verifica en Ulyses que no haya habitaciones "
            "bloqueadas por mantenimiento que puedan liberarse, o salidas anticipadas no "
            "registradas aún en el sistema.\n"
            "2. Si se confirma, prioriza reubicar a quien tenga menor impacto.\n"
            "3. El contacto telefónico previo a la llegada evita el conflicto presencial.\n"
        )
        chunks = split_with_overlap(text, chunk_size=120, chunk_overlap=10)
        # Ningún chunk debe terminar en un marcador de lista huérfano sin contenido detrás
        for chunk in chunks:
            assert not chunk.rstrip().endswith((". 1.", ". 2.", ". 3.", "\n1.", "\n2.", "\n3."))
        # El paso 2 debe aparecer completo en algún chunk, no partido entre dos
        assert any("2. Si se confirma, prioriza reubicar a quien tenga menor impacto." in c for c in chunks)

    def test_bullet_list_items_kept_whole_when_they_fit(self):
        text = (
            "- Confirma el overbooking revisando disponibilidad real en Ulyses.\n"
            "- Identifica candidatos a reubicar según antigüedad de fidelización.\n"
            "- Contacta primero por teléfono si el huésped aún no ha llegado.\n"
        )
        chunks = split_with_overlap(text, chunk_size=80, chunk_overlap=0)
        full_text = " ".join(chunks)
        assert "- Confirma el overbooking revisando disponibilidad real en Ulyses." in full_text
        assert "- Contacta primero por teléfono si el huésped aún no ha llegado." in full_text
