#!/usr/bin/env python3
"""
Reconstruye el índice de ChromaDB desde docs/.

Uso:
    python scripts/reindex.py

Requiere Ollama corriendo localmente con el modelo de embeddings descargado
(ver README.md, sección Instalación: `ollama pull nomic-embed-text`).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings  # noqa: E402
from src.embeddings.indexer import index_documents  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    result = index_documents(settings)
    print(
        f"Indexado completo: {result['upserted']} chunks actualizados, "
        f"{result['deleted']} obsoletos eliminados."
    )


if __name__ == "__main__":
    main()
