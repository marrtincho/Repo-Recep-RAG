"""Tests de src/generation/prompts.py."""

from __future__ import annotations

from src.generation.prompts import (
    CLARIFICATION_PREFIX,
    ESCALATION_MESSAGE,
    build_context_block,
    build_history_block,
    build_system_prompt,
    build_user_prompt,
)
from src.retrieval.search import SearchResult


def _result(text: str, source_path: str = "docs/procedimientos/overbooking.md") -> SearchResult:
    return SearchResult(chunk_id="x", text=text, similarity=0.9, metadata={"source_path": source_path})


class TestBuildSystemPrompt:
    def test_directo_mode_instructs_brief_answer(self):
        prompt = build_system_prompt("directo")
        assert "2-4 frases" in prompt.lower()

    def test_explicado_mode_instructs_context_and_reasoning(self):
        prompt = build_system_prompt("explicado")
        assert "por qué" in prompt.lower()

    def test_unknown_mode_falls_back_to_explicado(self):
        assert build_system_prompt("explicado") == build_system_prompt("algo-invalido")

    def test_safety_instruction_present_in_every_mode(self):
        for mode in ("directo", "explicado"):
            prompt = build_system_prompt(mode)
            assert ESCALATION_MESSAGE in prompt
            assert "SOLO con lo que diga el contexto" in prompt

    def test_mentions_citing_the_source(self):
        prompt = build_system_prompt("directo")
        assert "fuente" in prompt.lower()

    def test_clarification_instruction_absent_by_default(self):
        for mode in ("directo", "explicado"):
            prompt = build_system_prompt(mode)
            assert CLARIFICATION_PREFIX not in prompt

    def test_clarification_instruction_present_when_allowed(self):
        for mode in ("directo", "explicado"):
            prompt = build_system_prompt(mode, allow_clarification=True)
            assert CLARIFICATION_PREFIX in prompt


class TestBuildHistoryBlock:
    def test_empty_history_returns_empty_string(self):
        assert build_history_block(None) == ""
        assert build_history_block([]) == ""

    def test_formats_user_and_assistant_turns(self):
        block = build_history_block([("user", "¿cómo gestiono un overbooking?"), ("assistant", "¿el huésped ya llegó?")])
        assert "Personal: ¿cómo gestiono un overbooking?" in block
        assert "Asistente: ¿el huésped ya llegó?" in block

    def test_clarifies_history_is_not_a_source_of_facts(self):
        block = build_history_block([("user", "pregunta"), ("assistant", "respuesta")])
        assert "HECHOS" in block
        assert "CONTEXTO" in block


class TestBuildContextBlock:
    def test_empty_results_returns_placeholder(self):
        assert build_context_block([]) == "(sin contexto disponible)"

    def test_numbers_each_chunk_for_citation(self):
        block = build_context_block([_result("texto uno"), _result("texto dos")])
        assert "[1]" in block
        assert "[2]" in block

    def test_includes_source_filename_not_full_path(self):
        block = build_context_block([_result("texto", source_path="docs/directorios/contactos.md")])
        assert "contactos.md" in block
        assert "docs/directorios" not in block

    def test_missing_source_path_does_not_crash(self):
        result = SearchResult(chunk_id="x", text="texto", similarity=0.9, metadata={})
        block = build_context_block([result])
        assert "fuente desconocida" in block

    def test_chunk_text_included_in_block(self):
        block = build_context_block([_result("el contenido específico del chunk")])
        assert "el contenido específico del chunk" in block


class TestBuildUserPrompt:
    def test_includes_question_and_context(self):
        prompt = build_user_prompt("¿qué hago con un overbooking?", [_result("procedimiento de overbooking")])
        assert "¿qué hago con un overbooking?" in prompt
        assert "procedimiento de overbooking" in prompt

    def test_no_results_still_includes_question(self):
        prompt = build_user_prompt("pregunta sin contexto", [])
        assert "pregunta sin contexto" in prompt
        assert "sin contexto disponible" in prompt

    def test_no_history_means_no_history_block(self):
        prompt = build_user_prompt("pregunta", [], history=None)
        assert "CONVERSACIÓN PREVIA" not in prompt

    def test_history_included_when_present(self):
        prompt = build_user_prompt("¿y si se niega?", [], history=[("user", "¿qué hago con un overbooking?")])
        assert "CONVERSACIÓN PREVIA" in prompt
        assert "¿qué hago con un overbooking?" in prompt
        assert "¿y si se niega?" in prompt
