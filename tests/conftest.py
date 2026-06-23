"""Fixtures compartidos entre módulos de test."""

from __future__ import annotations

import uuid

import chromadb
import pytest


class FakeEmbeddingClient:
    """
    Cliente de embeddings de test, sin red ni Ollama.

    Si se le pasa `vectors` (texto -> vector exacto), lo usa para ese texto
    — útil cuando un test necesita similitudes predecibles y calculables a
    mano. Para cualquier texto no listado en `vectors`, genera un vector
    determinista por hash (mismo texto -> mismo vector siempre, pero sin
    relación numérica controlada), suficiente cuando un test solo necesita
    consistencia, no un valor de similitud concreto.
    """

    def __init__(self, vectors: dict[str, list[float]] | None = None, dim: int = 8) -> None:
        self.vectors = vectors or {}
        self.dim = dim
        self.calls: list[list[str]] = []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self.vectors.get(text, self._hash_vector(text)) for text in texts]

    def _hash_vector(self, text: str) -> list[float]:
        seed = sum(ord(c) for c in text) or 1
        return [((seed * (i + 1)) % 997) / 997 for i in range(self.dim)]


@pytest.fixture
def cosine_collection():
    """
    Colección ChromaDB efímera (en memoria) con métrica coseno, igual que en producción (ADR 0006).

    El nombre se genera con un UUID por test: chromadb.EphemeralClient()
    comparte estado interno entre instancias con settings idénticos dentro
    del mismo proceso, así que reutilizar un nombre fijo como
    "test_collection" contamina un test con los datos que dejó otro.
    """
    client = chromadb.EphemeralClient()
    name = f"test_{uuid.uuid4().hex}"
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


class FakeGenerationClient:
    """Cliente de generación de test, sin red ni Ollama: devuelve una respuesta fija o programable."""

    def __init__(self, response: str = "respuesta de prueba") -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []  # (system_prompt, user_prompt) de cada llamada

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response
