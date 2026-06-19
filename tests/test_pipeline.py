"""Test de integración de src/ingestion/pipeline.py — corre el pipeline completo de punta a punta."""

from __future__ import annotations

from pathlib import Path

from src.config import load_settings
from src.ingestion.models import Chunk
from src.ingestion.pipeline import load_documents

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestLoadDocumentsIntegration:
    """
    Corre el pipeline completo (config real + documentos reales en docs/) de punta a punta.

    A diferencia de los tests de cada chunker (que usan fixtures fijos), este
    test usa la configuración y los documentos de trabajo actuales del
    proyecto, así que sus aserciones son intencionalmente menos específicas:
    lo que valida es que el pipeline conecta todas las piezas sin romperse,
    no el contenido exacto de cada documento.
    """

    def test_pipeline_runs_end_to_end_without_errors(self):
        settings = load_settings()
        chunks = load_documents(settings)
        assert isinstance(chunks, list)
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_all_three_doc_types_represented(self):
        settings = load_settings()
        chunks = load_documents(settings)
        doc_types_found = {c.doc_type for c in chunks}
        assert doc_types_found == {"procedimientos", "directorios", "inventarios"}

    def test_chunk_ids_globally_unique_across_whole_corpus(self):
        """Los IDs deben ser únicos no solo dentro de un documento, sino en todo el corpus indexado."""
        settings = load_settings()
        chunks = load_documents(settings)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_missing_doc_type_folder_does_not_crash(self, tmp_path, monkeypatch):
        """Si una carpeta de documentos no existe aún, el pipeline debe avisar y seguir, no romperse."""
        settings = load_settings()
        # Apuntamos una de las rutas a una carpeta que no existe, sin tocar las demás.
        broken_settings = settings.__class__(
            **{**settings.__dict__, "inventarios_path": tmp_path / "no_existe"}
        )
        chunks = load_documents(broken_settings)
        assert all(c.doc_type != "inventarios" for c in chunks)
