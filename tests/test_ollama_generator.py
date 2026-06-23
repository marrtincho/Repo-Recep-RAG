"""Tests de src/generation/ollama_generator.py — cliente ollama mockeado, sin red ni Ollama real."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.generation.ollama_generator import GenerationError, OllamaGenerationClient


class TestGenerate:
    def test_returns_stripped_message_content(self):
        with patch("src.generation.ollama_generator.ollama.Client") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.chat.return_value = {"message": {"content": "  respuesta del modelo  \n"}}
            client = OllamaGenerationClient(model="llama3.1:8b", host="http://localhost:11434", temperature=0.2, max_tokens=512)

            result = client.generate("system", "user")

            assert result == "respuesta del modelo"

    def test_passes_model_messages_and_options_correctly(self):
        with patch("src.generation.ollama_generator.ollama.Client") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.chat.return_value = {"message": {"content": "ok"}}
            client = OllamaGenerationClient(model="mistral:7b", host="http://localhost:11434", temperature=0.3, max_tokens=256)

            client.generate("instrucciones del sistema", "pregunta del usuario")

            mock_instance.chat.assert_called_once_with(
                model="mistral:7b",
                messages=[
                    {"role": "system", "content": "instrucciones del sistema"},
                    {"role": "user", "content": "pregunta del usuario"},
                ],
                options={"temperature": 0.3, "num_predict": 256},
            )

    def test_connection_failure_raises_generation_error_with_actionable_message(self):
        with patch("src.generation.ollama_generator.ollama.Client") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.chat.side_effect = ConnectionError("connection refused")
            client = OllamaGenerationClient(model="llama3.1:8b", host="http://localhost:11434", temperature=0.2, max_tokens=512)

            with pytest.raises(GenerationError, match="ollama serve"):
                client.generate("system", "user")

    def test_error_message_mentions_the_configured_model(self):
        with patch("src.generation.ollama_generator.ollama.Client") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.chat.side_effect = RuntimeError("model not found")
            client = OllamaGenerationClient(model="llama3.1:8b", host="http://localhost:11434", temperature=0.2, max_tokens=512)

            with pytest.raises(GenerationError, match="llama3.1:8b"):
                client.generate("system", "user")

    def test_client_initialized_with_configured_host(self):
        with patch("src.generation.ollama_generator.ollama.Client") as mock_client_cls:
            OllamaGenerationClient(model="llama3.1:8b", host="http://example:9999", temperature=0.2, max_tokens=512)
            mock_client_cls.assert_called_once_with(host="http://example:9999")
