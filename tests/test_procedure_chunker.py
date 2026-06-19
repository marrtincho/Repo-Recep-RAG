"""Tests de src/ingestion/procedure_chunker.py."""

from __future__ import annotations

from pathlib import Path

from src.ingestion.procedure_chunker import chunk_procedure_document

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestChunkProcedureDocumentSynthetic:
    """Comportamiento controlado, con documentos pequeños construidos a mano."""

    def _valid_block(self, name: str = "Mi procedimiento") -> str:
        return (
            f"# {name}\n"
            "**Categoría:** Test\n"
            "**Última actualización:** 01/01/2026\n"
            "**Validado por:** Responsable\n"
            "### Resumen rápido\n"
            "- Paso uno\n"
            "- Paso dos\n"
            "### Procedimiento detallado\n"
            "1. Explicación del paso uno con más contexto.\n"
            "2. Explicación del paso dos con más contexto.\n"
        )

    def test_block_without_required_metadata_is_skipped(self):
        text = "# Solo un título\nAlgo de texto sin metadatos.\n### Resumen rápido\n- Paso\n"
        chunks = chunk_procedure_document(text, Path("doc.md"), chunk_size=500, chunk_overlap=50)
        assert chunks == []

    def test_block_with_partial_metadata_is_skipped(self):
        text = (
            "# Procedimiento incompleto\n"
            "**Categoría:** Test\n"
            "### Resumen rápido\n"
            "- Paso\n"
        )
        chunks = chunk_procedure_document(text, Path("doc.md"), chunk_size=500, chunk_overlap=50)
        assert chunks == []

    def test_valid_block_produces_chunks(self):
        chunks = chunk_procedure_document(self._valid_block(), Path("doc.md"), chunk_size=500, chunk_overlap=50)
        assert len(chunks) > 0
        assert all(c.doc_type == "procedimientos" for c in chunks)

    def test_resumen_rapido_tagged_as_modo_directo(self):
        chunks = chunk_procedure_document(self._valid_block(), Path("doc.md"), chunk_size=500, chunk_overlap=50)
        resumen = [c for c in chunks if c.metadata["subseccion"] == "Resumen rápido"]
        assert resumen
        assert all(c.metadata["modo"] == "directo" for c in resumen)

    def test_procedimiento_detallado_tagged_as_modo_explicado(self):
        chunks = chunk_procedure_document(self._valid_block(), Path("doc.md"), chunk_size=500, chunk_overlap=50)
        detallado = [c for c in chunks if c.metadata["subseccion"] == "Procedimiento detallado"]
        assert detallado
        assert all(c.metadata["modo"] == "explicado" for c in detallado)

    def test_other_subsections_tagged_as_modo_ambos(self):
        text = self._valid_block() + "### Cuándo escalar\n- Si pasa X, escalar a Y\n"
        chunks = chunk_procedure_document(text, Path("doc.md"), chunk_size=500, chunk_overlap=50)
        escalar = [c for c in chunks if c.metadata["subseccion"] == "Cuándo escalar"]
        assert escalar
        assert all(c.metadata["modo"] == "ambos" for c in escalar)

    def test_metadata_propagated_to_every_chunk_of_the_block(self):
        chunks = chunk_procedure_document(self._valid_block("Overbooking"), Path("doc.md"), chunk_size=500, chunk_overlap=50)
        assert all(c.metadata["nombre_procedimiento"] == "Overbooking" for c in chunks)
        assert all(c.metadata["categoria"] == "Test" for c in chunks)
        assert all(c.metadata["validado_por"] == "Responsable" for c in chunks)

    def test_multiple_valid_blocks_in_same_file_both_chunked(self):
        text = self._valid_block("Primero") + "\n" + self._valid_block("Segundo")
        chunks = chunk_procedure_document(text, Path("doc.md"), chunk_size=500, chunk_overlap=50)
        nombres = {c.metadata["nombre_procedimiento"] for c in chunks}
        assert nombres == {"Primero", "Segundo"}

    def test_valid_block_mixed_with_invalid_block_only_valid_is_kept(self):
        invalid = "# Plantilla\nTexto explicativo sin metadatos.\n### Resumen rápido\n- placeholder\n"
        text = invalid + "\n" + self._valid_block("Real")
        chunks = chunk_procedure_document(text, Path("doc.md"), chunk_size=500, chunk_overlap=50)
        assert chunks
        assert all(c.metadata["nombre_procedimiento"] == "Real" for c in chunks)

    def test_block_with_metadata_but_no_h3_subsections_is_skipped(self):
        text = (
            "# Procedimiento raro\n"
            "**Categoría:** Test\n"
            "**Última actualización:** 01/01/2026\n"
            "**Validado por:** Responsable\n"
            "Solo texto plano, sin subsecciones H3.\n"
        )
        chunks = chunk_procedure_document(text, Path("doc.md"), chunk_size=500, chunk_overlap=50)
        assert chunks == []

    def test_no_h1_blocks_returns_empty_list(self):
        text = "## Esto no es un H1\ncontenido\n"
        chunks = chunk_procedure_document(text, Path("doc.md"), chunk_size=500, chunk_overlap=50)
        assert chunks == []

    def test_chunk_ids_unique_within_document(self):
        text = self._valid_block("Primero") + "\n" + self._valid_block("Segundo")
        chunks = chunk_procedure_document(text, Path("doc.md"), chunk_size=500, chunk_overlap=50)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_horizontal_rule_inside_subsection_is_stripped(self):
        text = self._valid_block() + "\n---\n"
        chunks = chunk_procedure_document(text, Path("doc.md"), chunk_size=500, chunk_overlap=50)
        assert all("---" not in c.text for c in chunks)


class TestChunkProcedureDocumentRealFixture:
    """Validación contra el documento real subido por el usuario."""

    def test_template_block_is_skipped_real_example_is_kept(self):
        path = FIXTURES / "procedimientos" / "plantilla_procedimiento_operativo.md"
        text = path.read_text(encoding="utf-8")
        chunks = chunk_procedure_document(text, path, chunk_size=500, chunk_overlap=50)

        nombres = {c.metadata["nombre_procedimiento"] for c in chunks}
        assert nombres == {"Ejemplo aplicado: Gestión de overbooking"}
        assert "Plantilla: Documentación de procedimiento operativo" not in nombres

    def test_all_six_subsections_present(self):
        path = FIXTURES / "procedimientos" / "plantilla_procedimiento_operativo.md"
        text = path.read_text(encoding="utf-8")
        chunks = chunk_procedure_document(text, path, chunk_size=500, chunk_overlap=50)

        subsecciones = {c.metadata["subseccion"] for c in chunks}
        assert subsecciones == {
            "Resumen rápido",
            "Procedimiento detallado",
            "Casos especiales / excepciones",
            "Cuándo escalar",
            "Preguntas habituales relacionadas",
            "Notas internas",
        }

    def test_numbered_steps_in_procedimiento_detallado_not_split_mid_step(self):
        path = FIXTURES / "procedimientos" / "plantilla_procedimiento_operativo.md"
        text = path.read_text(encoding="utf-8")
        chunks = chunk_procedure_document(text, path, chunk_size=500, chunk_overlap=50)

        detallado = [c.text for c in chunks if c.metadata["subseccion"] == "Procedimiento detallado"]
        full_text = " ".join(detallado)
        assert "2. Si se confirma, prioriza reubicar a quien tenga menor impacto" in full_text
        assert "4. La compensación estándar" in full_text
        for chunk_text in detallado:
            assert not chunk_text.rstrip().endswith((" 1.", " 2.", " 3.", " 4."))

    def test_metadata_extracted_correctly_from_real_example(self):
        path = FIXTURES / "procedimientos" / "plantilla_procedimiento_operativo.md"
        text = path.read_text(encoding="utf-8")
        chunks = chunk_procedure_document(text, path, chunk_size=500, chunk_overlap=50)

        assert all(c.metadata["categoria"] == "Reservas" for c in chunks)
        assert all(c.metadata["ultima_actualizacion"] == "17/06/2026" for c in chunks)
