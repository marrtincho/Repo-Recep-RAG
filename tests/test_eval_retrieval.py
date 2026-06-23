"""
Tests del script de evaluación de retrieval.

Solo se testea la lógica pura (parseo de casos, formato del CSV) —
la parte que llama a Ollama/ChromaDB no se puede testear en el sandbox.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# Importar la función de parseo directamente del módulo
import importlib.util, sys

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "eval_retrieval.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("eval_retrieval", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # El módulo hace sys.path.insert al importarse — necesitamos suprimir ese efecto
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


class TestLoadCases:
    def test_parses_basic_csv(self, mod, tmp_path):
        csv = tmp_path / "cases.csv"
        csv.write_text(
            "pregunta,documento_esperado,nota\n"
            "como hago un check in?,Proceso de check-in.md,test\n"
        )
        cases = mod._load_cases(csv)
        assert len(cases) == 1
        assert cases[0] == ("como hago un check in?", "Proceso de check-in.md", "test")

    def test_skips_comment_lines(self, mod, tmp_path):
        csv = tmp_path / "cases.csv"
        csv.write_text(
            "# CHECK-IN\n"
            "como hago un check in?,Proceso de check-in.md,\n"
            "# PARKING\n"
            "como cargo un parking?,Parking.md,\n"
        )
        cases = mod._load_cases(csv)
        assert len(cases) == 2

    def test_skips_header_row(self, mod, tmp_path):
        csv = tmp_path / "cases.csv"
        csv.write_text(
            "pregunta,documento_esperado,nota\n"
            "pregunta real?,Documento.md,\n"
        )
        cases = mod._load_cases(csv)
        assert len(cases) == 1
        assert cases[0][0] == "pregunta real?"

    def test_empty_note_is_empty_string(self, mod, tmp_path):
        csv = tmp_path / "cases.csv"
        csv.write_text("como hago un check in?,Proceso de check-in.md\n")
        cases = mod._load_cases(csv)
        assert cases[0][2] == ""

    def test_note_can_contain_commas(self, mod, tmp_path):
        csv = tmp_path / "cases.csv"
        csv.write_text("pregunta,doc.md,nota con, coma interna\n")
        cases = mod._load_cases(csv)
        assert cases[0][2] == "nota con, coma interna"

    def test_real_cases_file_loads_without_error(self, mod):
        cases_path = Path(__file__).resolve().parent.parent / "eval" / "retrieval_cases.csv"
        cases = mod._load_cases(cases_path)
        assert len(cases) >= 30
        docs = {doc for _, doc, _ in cases}
        assert "Proceso de check-in.md" in docs
        assert "mapeo_conceptos_facturacion.md" in docs
        assert "directorio_contactos_hotel.md" in docs