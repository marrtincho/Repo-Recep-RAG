"""Tests de src/ingestion/table_chunker.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.table_chunker import chunk_table_document

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestChunkTableDocumentSynthetic:
    """Comportamiento controlado, con documentos pequeños construidos a mano."""

    def test_rejects_unsupported_doc_type(self):
        with pytest.raises(ValueError, match="doc_type"):
            chunk_table_document("# X\n## S\n", doc_type="procedimientos", source_path=Path("x.md"), chunk_size=200, chunk_overlap=0)

    def test_keeps_only_rows_with_content_beyond_key_column(self):
        text = (
            "# Doc\n"
            "## Seccion\n"
            "| Nombre | Telefono |\n"
            "|---|---|\n"
            "| Ana | 600111222 |\n"
            "| Luis | |\n"
        )
        chunks = chunk_table_document(text, "directorios", Path("doc.md"), chunk_size=200, chunk_overlap=0)
        assert len(chunks) == 1
        assert "Ana" in chunks[0].text
        assert "600111222" in chunks[0].text

    def test_section_with_no_table_falls_back_to_bullets(self):
        text = "# Doc\n## Notas\n- Primera nota\n- Segunda nota\n"
        chunks = chunk_table_document(text, "inventarios", Path("doc.md"), chunk_size=200, chunk_overlap=0)
        assert [c.text for c in chunks] == ["Primera nota", "Segunda nota"]
        assert all(c.metadata["tipo_entrada"] == "nota" for c in chunks)

    def test_fully_empty_table_produces_zero_chunks(self):
        text = "# Doc\n## Seccion\n| Nombre | Telefono |\n|---|---|\n| Ana | |\n| Luis | |\n"
        chunks = chunk_table_document(text, "directorios", Path("doc.md"), chunk_size=200, chunk_overlap=0)
        assert chunks == []

    def test_no_h2_sections_returns_empty_list(self):
        text = "# Solo un titulo, sin secciones H2\ncontenido suelto\n"
        chunks = chunk_table_document(text, "directorios", Path("doc.md"), chunk_size=200, chunk_overlap=0)
        assert chunks == []

    def test_long_row_text_is_split_with_overlap(self):
        long_value = "palabra " * 80  # fuerza superar chunk_size
        text = f"# Doc\n## Seccion\n| Nombre | Notas |\n|---|---|\n| Ana | {long_value.strip()} |\n"
        chunks = chunk_table_document(text, "directorios", Path("doc.md"), chunk_size=100, chunk_overlap=10)
        assert len(chunks) > 1
        assert all(c.metadata["categoria"] == "Seccion" for c in chunks)

    def test_chunk_ids_are_unique_within_document(self):
        text = (
            "# Doc\n"
            "## Seccion\n"
            "| Nombre | Tel |\n"
            "|---|---|\n"
            "| Ana | 1 |\n"
            "| Luis | 2 |\n"
        )
        chunks = chunk_table_document(text, "directorios", Path("doc.md"), chunk_size=200, chunk_overlap=0)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_source_path_and_doc_type_propagated(self):
        text = "# Doc\n## Seccion\n| Nombre | Tel |\n|---|---|\n| Ana | 1 |\n"
        path = Path("mi_archivo.md")
        chunks = chunk_table_document(text, "inventarios", path, chunk_size=200, chunk_overlap=0)
        assert chunks[0].source_path == path
        assert chunks[0].doc_type == "inventarios"


class TestChunkTableDocumentRealFixtures:
    """Validación contra los documentos reales subidos por el usuario."""

    def test_directorio_contactos_produces_expected_chunks(self):
        path = FIXTURES / "directorios" / "directorio_contactos_hotel.md"
        text = path.read_text(encoding="utf-8")
        chunks = chunk_table_document(text, "directorios", path, chunk_size=200, chunk_overlap=0)

        # Solo hay 2 filas de tabla con datos reales (Dirección, Emergencias generales)
        # más 3 viñetas de la sección de notas de mantenimiento = 5 chunks
        assert len(chunks) == 5

        tabla_chunks = [c for c in chunks if c.metadata["tipo_entrada"] == "tabla"]
        nota_chunks = [c for c in chunks if c.metadata["tipo_entrada"] == "nota"]
        assert len(tabla_chunks) == 2
        assert len(nota_chunks) == 3

        direccion = next(c for c in tabla_chunks if c.metadata["categoria"] == "Departamentos internos")
        assert "Carlos Boga" in direccion.text
        assert "4016" in direccion.text

        emergencias = next(c for c in tabla_chunks if c.metadata["categoria"] == "Emergencias")
        assert "112" in emergencias.text

        # La sección "Proveedores externos" es plantilla vacía: no debe aportar chunks
        assert all(c.metadata["categoria"] != "Proveedores externos" for c in chunks)

    def test_ubicaciones_inventario_produces_only_notes_chunks(self):
        """El fixture de inventario es una plantilla sin rellenar: ninguna tabla tiene datos reales."""
        path = FIXTURES / "inventarios" / "ubicaciones_inventario_huespedes.md"
        text = path.read_text(encoding="utf-8")
        chunks = chunk_table_document(text, "inventarios", path, chunk_size=200, chunk_overlap=0)

        assert len(chunks) == 2
        assert all(c.metadata["tipo_entrada"] == "nota" for c in chunks)
        assert all(c.metadata["categoria"] == "Notas de mantenimiento de este documento" for c in chunks)
