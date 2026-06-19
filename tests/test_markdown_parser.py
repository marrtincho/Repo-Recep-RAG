"""Tests de src/ingestion/markdown_parser.py — entradas sintéticas, sin depender de documentos reales."""

from __future__ import annotations

from src.ingestion.markdown_parser import (
    extract_bullets,
    leading_text_before_any_heading,
    parse_markdown_table,
    parse_metadata_block,
    slugify,
    split_by_heading,
    strip_horizontal_rules,
)


class TestSlugify:
    def test_removes_accents_and_lowercases(self):
        assert slugify("Última actualización") == "ultima-actualizacion"

    def test_replaces_spaces_and_punctuation_with_single_hyphen(self):
        assert slugify("Procedimiento detallado!") == "procedimiento-detallado"

    def test_strips_leading_and_trailing_hyphens(self):
        assert slugify("  [Nombre del procedimiento]  ") == "nombre-del-procedimiento"


class TestSplitByHeading:
    def test_splits_top_level_blocks(self):
        text = "# Uno\ncontenido uno\n# Dos\ncontenido dos\n"
        blocks = split_by_heading(text, level=1)
        assert [b.title for b in blocks] == ["Uno", "Dos"]
        assert blocks[0].body == "contenido uno"
        assert blocks[1].body == "contenido dos"

    def test_ignores_headings_of_other_levels(self):
        text = "# Titulo\n## Sub\ntexto\n# Otro\nfinal\n"
        blocks = split_by_heading(text, level=1)
        assert len(blocks) == 2
        assert "## Sub" in blocks[0].body  # queda anidado, sin procesar

    def test_text_before_first_heading_is_discarded(self):
        text = "preambulo sin encabezado\n# Titulo\ncontenido\n"
        blocks = split_by_heading(text, level=1)
        assert len(blocks) == 1
        assert blocks[0].title == "Titulo"

    def test_nested_level_extraction(self):
        text = "# Padre\n### Hijo A\ntexto a\n### Hijo B\ntexto b\n"
        parent = split_by_heading(text, level=1)[0]
        children = split_by_heading(parent.body, level=3)
        assert [c.title for c in children] == ["Hijo A", "Hijo B"]

    def test_no_matching_headings_returns_empty_list(self):
        assert split_by_heading("solo texto plano, sin encabezados", level=2) == []


class TestLeadingTextBeforeAnyHeading:
    def test_stops_at_first_nested_heading(self):
        body = "linea de metadatos\notra linea\n### Subseccion\nesto no debe incluirse"
        assert leading_text_before_any_heading(body) == "linea de metadatos\notra linea"

    def test_returns_full_text_if_no_heading_present(self):
        body = "todo esto es preambulo\nsin ningun encabezado"
        assert leading_text_before_any_heading(body) == body


class TestParseMetadataBlock:
    def test_extracts_bold_key_value_pairs(self):
        text = "**Categoría:** Reservas\n**Última actualización:** 17/06/2026\n"
        metadata = parse_metadata_block(text)
        assert metadata == {"categoria": "Reservas", "ultima_actualizacion": "17/06/2026"}

    def test_ignores_non_matching_lines(self):
        text = "texto normal\n**Validado por:** Responsable de recepción\nmás texto normal\n"
        metadata = parse_metadata_block(text)
        assert metadata == {"validado_por": "Responsable de recepción"}

    def test_empty_text_returns_empty_dict(self):
        assert parse_metadata_block("") == {}

    def test_placeholder_only_text_with_no_bold_lines_returns_empty(self):
        text = "Usa esta estructura para cada procedimiento que documentes."
        assert parse_metadata_block(text) == {}


class TestExtractBullets:
    def test_extracts_dash_bullets(self):
        text = "- Paso uno\n- Paso dos\ntexto suelto que no es viñeta\n- Paso tres\n"
        assert extract_bullets(text) == ["Paso uno", "Paso dos", "Paso tres"]

    def test_no_bullets_returns_empty_list(self):
        assert extract_bullets("solo texto, ninguna viñeta aquí") == []


class TestParseMarkdownTable:
    def test_parses_simple_table_into_row_dicts(self):
        text = (
            "| Nombre | Telefono |\n"
            "|---|---|\n"
            "| Ana | 111 |\n"
            "| Luis | 222 |\n"
        )
        rows = parse_markdown_table(text)
        assert rows == [
            {"Nombre": "Ana", "Telefono": "111"},
            {"Nombre": "Luis", "Telefono": "222"},
        ]

    def test_no_table_returns_empty_list(self):
        assert parse_markdown_table("texto normal sin tabla") == []

    def test_tolerates_rows_with_fewer_cells_than_header(self):
        text = "| A | B | C |\n|---|---|---|\n| solo-a |\n"
        rows = parse_markdown_table(text)
        assert rows == [{"A": "solo-a", "B": "", "C": ""}]

    def test_ignores_non_table_lines_interspersed(self):
        text = (
            "texto antes\n"
            "| A | B |\n"
            "|---|---|\n"
            "texto entre medio que no empieza con pipe\n"
            "| 1 | 2 |\n"
        )
        rows = parse_markdown_table(text)
        assert rows == [{"A": "1", "B": "2"}]


class TestStripHorizontalRules:
    def test_removes_standalone_dash_lines(self):
        text = "parrafo uno\n---\nparrafo dos\n"
        assert strip_horizontal_rules(text) == "parrafo uno\nparrafo dos"

    def test_does_not_remove_table_separator_rows(self):
        # Una fila separadora de tabla incluye pipes, no es una regla horizontal pura
        text = "| A | B |\n|---|---|\n| 1 | 2 |"
        assert strip_horizontal_rules(text) == text
