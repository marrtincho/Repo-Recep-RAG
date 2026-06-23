"""
Tests de src/embeddings/indexer.py.

No requieren Ollama: el cliente de embeddings es un fake determinista, y
ChromaDB se usa en modo efímero (en memoria, sin persistencia a disco), que
no necesita red ni servidor externo.
"""

from __future__ import annotations

from pathlib import Path

import chromadb
import pytest

from src.embeddings.indexer import DEFAULT_COLLECTION_NAME, get_collection, index_chunks
from src.ingestion.models import Chunk
from tests.conftest import FakeEmbeddingClient


class MismatchedEmbeddingClient:
    """Cliente que deliberadamente devuelve menos vectores de los esperados, para testear validación."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0]] if texts else []


@pytest.fixture
def collection() -> chromadb.Collection:
    client = chromadb.EphemeralClient()
    return client.get_or_create_collection(name="test_collection")


def _make_chunk(chunk_id: str, text: str = "texto de prueba", doc_type: str = "directorios") -> Chunk:
    return Chunk(
        text=text,
        doc_type=doc_type,
        source_path=Path(f"docs/{doc_type}/ejemplo.md"),
        chunk_id=chunk_id,
        metadata={"categoria": "Test"},
    )


class TestIndexChunks:
    def test_upserts_all_chunks_with_correct_count(self, collection):
        chunks = [_make_chunk("a"), _make_chunk("b"), _make_chunk("c")]
        result = index_chunks(chunks, FakeEmbeddingClient(), collection)
        assert result == {"upserted": 3, "deleted": 0}
        assert collection.count() == 3

    def test_metadata_includes_doc_type_and_source_path(self, collection):
        chunk = _make_chunk("a", doc_type="inventarios")
        index_chunks([chunk], FakeEmbeddingClient(), collection)
        stored = collection.get(ids=["a"])
        assert stored["metadatas"][0]["doc_type"] == "inventarios"
        assert stored["metadatas"][0]["source_path"] == str(chunk.source_path)
        assert stored["metadatas"][0]["categoria"] == "Test"

    def test_reindexing_same_chunks_is_idempotent_not_duplicated(self, collection):
        chunks = [_make_chunk("a"), _make_chunk("b")]
        index_chunks(chunks, FakeEmbeddingClient(), collection)
        index_chunks(chunks, FakeEmbeddingClient(), collection)
        assert collection.count() == 2

    def test_reindexing_with_updated_text_overwrites_not_duplicates(self, collection):
        index_chunks([_make_chunk("a", text="version vieja")], FakeEmbeddingClient(), collection)
        index_chunks([_make_chunk("a", text="version nueva")], FakeEmbeddingClient(), collection)
        assert collection.count() == 1
        assert collection.get(ids=["a"])["documents"][0] == "version nueva"

    def test_chunk_removed_from_corpus_is_pruned_from_collection(self, collection):
        index_chunks([_make_chunk("a"), _make_chunk("b"), _make_chunk("c")], FakeEmbeddingClient(), collection)
        result = index_chunks([_make_chunk("a"), _make_chunk("b")], FakeEmbeddingClient(), collection)
        assert result == {"upserted": 2, "deleted": 1}
        assert collection.count() == 2
        assert collection.get(ids=["c"])["ids"] == []

    def test_empty_chunk_list_prunes_entire_collection(self, collection):
        index_chunks([_make_chunk("a"), _make_chunk("b")], FakeEmbeddingClient(), collection)
        result = index_chunks([], FakeEmbeddingClient(), collection)
        assert result == {"upserted": 0, "deleted": 2}
        assert collection.count() == 0

    def test_batching_makes_multiple_embed_batch_calls(self, collection):
        chunks = [_make_chunk(str(i)) for i in range(5)]
        fake_client = FakeEmbeddingClient()
        index_chunks(chunks, fake_client, collection, batch_size=2)
        assert len(fake_client.calls) == 3  # 2 + 2 + 1
        assert collection.count() == 5

    def test_mismatched_embedding_count_raises_value_error(self, collection):
        chunks = [_make_chunk("a"), _make_chunk("b")]
        with pytest.raises(ValueError, match="vectores"):
            index_chunks(chunks, MismatchedEmbeddingClient(), collection)


class TestGetCollection:
    """get_collection usa PersistentClient (almacenamiento en disco), por eso usa tmp_path en vez del fixture efímero."""

    def test_creates_collection_with_cosine_metric(self, tmp_path):
        collection = get_collection(tmp_path)
        assert collection.metadata["hnsw:space"] == "cosine"

    def test_reopening_same_collection_succeeds(self, tmp_path):
        get_collection(tmp_path)
        collection = get_collection(tmp_path)  # debe abrir la existente sin lanzar error
        assert collection.metadata["hnsw:space"] == "cosine"

    def test_existing_collection_with_different_metric_raises_clear_error(self, tmp_path):
        # Simula una colección creada antes de fijar la métrica explícitamente (L2 por defecto)
        client = chromadb.PersistentClient(path=str(tmp_path))
        client.get_or_create_collection(name=DEFAULT_COLLECTION_NAME, metadata={"hnsw:space": "l2"})

        with pytest.raises(ValueError, match="reindexa"):
            get_collection(tmp_path)

    def test_creates_chroma_db_path_if_missing(self, tmp_path):
        target = tmp_path / "no_existe_todavia" / "chroma_db"
        assert not target.exists()
        get_collection(target)
        assert target.exists()
