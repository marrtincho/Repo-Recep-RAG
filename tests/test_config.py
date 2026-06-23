"""Tests del módulo de configuración (src/config.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import ConfigError, load_settings

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_CONFIG_PATH = REPO_ROOT / "config" / "settings.yaml"


def test_load_real_settings_yaml_succeeds():
    """El settings.yaml versionado en el repo debe cargar sin errores."""
    settings = load_settings(REAL_CONFIG_PATH)
    assert settings.embedding_model == "bge-m3"
    assert 0.0 <= settings.confidence_threshold <= 1.0
    assert settings.top_k > 0
    assert settings.max_history_turns > 0


def test_paths_are_resolved_relative_to_repo_root():
    """Las rutas de la config deben resolverse a rutas absolutas dentro del repo."""
    settings = load_settings(REAL_CONFIG_PATH)
    assert settings.docs_root.is_absolute()
    assert settings.docs_root == REPO_ROOT / "docs"
    assert settings.chroma_db_path == REPO_ROOT / "data" / "chroma_db"


def test_doc_type_paths_covers_all_document_types():
    """El mapa doc_type_paths debe exponer las cuatro categorías documentales."""
    settings = load_settings(REAL_CONFIG_PATH)
    assert set(settings.doc_type_paths) == {"procedimientos", "directorios", "inventarios", "referencias"}


def test_chunking_profiles_loaded_for_each_doc_type():
    """Cada tipo de documento debe tener su propio perfil de chunking."""
    settings = load_settings(REAL_CONFIG_PATH)
    for doc_type in ("procedimientos", "directorios", "inventarios", "referencias"):
        profile = settings.chunking[doc_type]
        assert profile.chunk_size > 0
        assert profile.chunk_overlap >= 0
        assert profile.strategy


def test_missing_file_raises_config_error(tmp_path):
    """Apuntar a un archivo inexistente debe fallar con un mensaje claro, no con un traceback crudo."""
    missing = tmp_path / "no_existe.yaml"
    with pytest.raises(ConfigError, match="No se encontró"):
        load_settings(missing)


def test_missing_required_key_raises_config_error(tmp_path):
    """Un settings.yaml incompleto debe fallar rápido, señalando la clave exacta que falta.

    Incluye todas las secciones salvo 'generation.mode_default', para que el
    fallo sea determinista y apunte específicamente a esa clave ausente.
    """
    incomplete = tmp_path / "settings.yaml"
    incomplete.write_text(
        """
models:
  embedding: nomic-embed-text
  generation: llama3.1:8b
  ollama_host: http://localhost:11434
paths:
  docs_root: docs/
  procedimientos: docs/procedimientos/
  directorios: docs/directorios/
  inventarios: docs/inventarios/
  referencias: docs/referencias/
  chroma_db: data/chroma_db/
  gap_log: metrics/gap_log.csv
  feedback_log: metrics/feedback_log.csv
chunking:
  procedimientos: {chunk_size: 500, chunk_overlap: 50, strategy: by_section}
  directorios: {chunk_size: 200, chunk_overlap: 0, strategy: by_entry}
  inventarios: {chunk_size: 200, chunk_overlap: 0, strategy: by_entry}
  referencias: {chunk_size: 550, chunk_overlap: 0, strategy: by_entry}
retrieval:
  confidence_threshold: 0.65
  top_k: 3
generation:
  temperature: 0.2
  max_tokens: 512
conversation:
  max_history_turns: 3
logging:
  level: INFO
  log_file: metrics/interactions.log
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="generation.mode_default"):
        load_settings(incomplete)


def test_invalid_yaml_raises_config_error(tmp_path):
    """YAML mal formado debe fallar con ConfigError, no con una excepción genérica de yaml."""
    broken = tmp_path / "settings.yaml"
    broken.write_text("models: [unbalanced\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_settings(broken)
