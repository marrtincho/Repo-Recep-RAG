"""
Carga y validación de la configuración central del proyecto.

Toda la configuración ajustable (modelos, rutas, umbrales, chunking) vive en
config/settings.yaml. Este módulo es el ÚNICO punto de entrada para leerla:
ningún otro módulo debe abrir ese YAML directamente ni hardcodear sus valores,
para que recalibrar el sistema (p. ej. el umbral de confianza) nunca implique
tocar lógica de negocio.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Ruta por defecto a settings.yaml, relativa a la raíz del repo.
# Este archivo vive en src/config.py, así que la raíz es dos niveles arriba.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"


class ConfigError(Exception):
    """Error al cargar o validar config/settings.yaml."""


@dataclass(frozen=True)
class ChunkingProfile:
    """Parámetros de chunking para un tipo de documento concreto."""

    chunk_size: int
    chunk_overlap: int
    strategy: str


@dataclass(frozen=True)
class Settings:
    """Configuración tipada y validada, lista para usar en cualquier capa."""

    # models
    embedding_model: str
    generation_model: str
    ollama_host: str

    # paths (ya resueltas a rutas absolutas)
    docs_root: Path
    procedimientos_path: Path
    directorios_path: Path
    inventarios_path: Path
    chroma_db_path: Path
    gap_log_path: Path
    feedback_log_path: Path

    # chunking, una entrada por tipo de documento
    chunking: dict[str, ChunkingProfile]

    # retrieval
    confidence_threshold: float
    top_k: int

    # generation
    mode_default: str
    temperature: float
    max_tokens: int

    # logging
    log_level: str
    log_file: Path

    @property
    def doc_type_paths(self) -> dict[str, Path]:
        """Mapa tipo de documento -> carpeta fuente. Usado por el pipeline de ingesta."""
        return {
            "procedimientos": self.procedimientos_path,
            "directorios": self.directorios_path,
            "inventarios": self.inventarios_path,
        }


def _require(data: dict[str, Any], *keys: str) -> Any:
    """Navega un dict anidado; lanza ConfigError con un mensaje claro si falta una clave."""
    node: Any = data
    seen: list[str] = []
    for key in keys:
        seen.append(key)
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(f"Falta la clave '{'.'.join(seen)}' en settings.yaml")
        node = node[key]
    return node


def load_settings(config_path: Path | str = DEFAULT_CONFIG_PATH) -> Settings:
    """
    Carga config/settings.yaml y devuelve un objeto Settings validado.

    Lanza ConfigError si el archivo no existe, no es YAML válido, o le falta
    alguna clave requerida. Fallar rápido y con un mensaje claro aquí evita
    errores confusos más adelante en capas que asumen una config ya válida.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise ConfigError(f"No se encontró el archivo de configuración: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ConfigError(f"settings.yaml no es YAML válido: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("settings.yaml debe definir un mapeo de nivel superior")

    repo_root = config_path.resolve().parent.parent

    def _resolve(relative: str) -> Path:
        return (repo_root / relative).resolve()

    chunking_raw = _require(raw, "chunking")
    chunking = {
        doc_type: ChunkingProfile(
            chunk_size=_require(chunking_raw, doc_type, "chunk_size"),
            chunk_overlap=_require(chunking_raw, doc_type, "chunk_overlap"),
            strategy=_require(chunking_raw, doc_type, "strategy"),
        )
        for doc_type in chunking_raw
    }

    return Settings(
        embedding_model=_require(raw, "models", "embedding"),
        generation_model=_require(raw, "models", "generation"),
        ollama_host=_require(raw, "models", "ollama_host"),
        docs_root=_resolve(_require(raw, "paths", "docs_root")),
        procedimientos_path=_resolve(_require(raw, "paths", "procedimientos")),
        directorios_path=_resolve(_require(raw, "paths", "directorios")),
        inventarios_path=_resolve(_require(raw, "paths", "inventarios")),
        chroma_db_path=_resolve(_require(raw, "paths", "chroma_db")),
        gap_log_path=_resolve(_require(raw, "paths", "gap_log")),
        feedback_log_path=_resolve(_require(raw, "paths", "feedback_log")),
        chunking=chunking,
        confidence_threshold=float(_require(raw, "retrieval", "confidence_threshold")),
        top_k=int(_require(raw, "retrieval", "top_k")),
        mode_default=_require(raw, "generation", "mode_default"),
        temperature=float(_require(raw, "generation", "temperature")),
        max_tokens=int(_require(raw, "generation", "max_tokens")),
        log_level=_require(raw, "logging", "level"),
        log_file=_resolve(_require(raw, "logging", "log_file")),
    )
