"""Tests de src/embeddings/ollama_client.py — cliente ollama mockeado, sin red ni Ollama real."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.embeddings.ollama_client import EmbeddingError, OllamaEmbeddingClient


class TestEmbedBatch:
    def test_empty_list_returns_empty_list_without_calling_client(self):
        with patch("src.embeddings.ollama_client.ollama.Client") as mock_client_cls:
            client = OllamaEmbeddingClient(model="nomic-embed-text", host="http://localhost:11434")
            result = client.embed_batch([])
            assert result == []
            mock_client_cls.return_value.embed.assert_not_called()

    def test_uses_batch_embed_api_when_available(self):
        with patch("src.embeddings.ollama_client.ollama.Client") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.embed.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
            client = OllamaEmbeddingClient(model="nomic-embed-text", host="http://localhost:11434")

            result = client.embed_batch(["texto uno", "texto dos"])

            assert result == [[0.1, 0.2], [0.3, 0.4]]
            mock_instance.embed.assert_called_once_with(model="nomic-embed-text", input=["texto uno", "texto dos"])

    def test_falls_back_to_per_text_embeddings_when_embed_not_available(self):
        with patch("src.embeddings.ollama_client.ollama.Client") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            del mock_instance.embed  # simula un cliente ollama-python antiguo sin embed()
            mock_instance.embeddings.side_effect = [
                {"embedding": [0.1, 0.2]},
                {"embedding": [0.3, 0.4]},
            ]
            client = OllamaEmbeddingClient(model="nomic-embed-text", host="http://localhost:11434")

            result = client.embed_batch(["texto uno", "texto dos"])

            assert result == [[0.1, 0.2], [0.3, 0.4]]
            assert mock_instance.embeddings.call_count == 2

    def test_connection_failure_raises_embedding_error_with_actionable_message(self):
        with patch("src.embeddings.ollama_client.ollama.Client") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.embed.side_effect = ConnectionError("connection refused")
            client = OllamaEmbeddingClient(model="nomic-embed-text", host="http://localhost:11434")

            with pytest.raises(EmbeddingError, match="ollama serve"):
                client.embed_batch(["texto"])

    def test_error_message_mentions_the_configured_model(self):
        with patch("src.embeddings.ollama_client.ollama.Client") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.embed.side_effect = RuntimeError("model not found")
            client = OllamaEmbeddingClient(model="nomic-embed-text", host="http://localhost:11434")

            with pytest.raises(EmbeddingError, match="nomic-embed-text"):
                client.embed_batch(["texto"])

    def test_client_initialized_with_configured_host(self):
        with patch("src.embeddings.ollama_client.ollama.Client") as mock_client_cls:
            OllamaEmbeddingClient(model="nomic-embed-text", host="http://example:9999")
            mock_client_cls.assert_called_once_with(host="http://example:9999")
