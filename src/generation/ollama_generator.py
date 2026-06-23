"""
Cliente de generación sobre Ollama.

Envoltorio fino sobre la librería oficial `ollama`, análogo a
src/embeddings/ollama_client.py pero para el modelo de chat/generación
(p. ej. llama3.1:8b o mistral:7b), no el de embeddings.
"""

from __future__ import annotations

import ollama


class GenerationError(Exception):
    """Error al generar una respuesta vía Ollama (servidor no disponible, modelo no descargado, etc.)."""


class OllamaGenerationClient:
    """Genera respuestas de texto usando un modelo de chat servido por Ollama."""

    def __init__(self, model: str, host: str, temperature: float, max_tokens: int) -> None:
        self.model = model
        self.host = host
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = ollama.Client(host=host)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Genera la respuesta del modelo dado un system prompt y un user prompt."""
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            )
            return response["message"]["content"].strip()
        except Exception as exc:  # la librería ollama puede lanzar varios tipos según el fallo
            raise GenerationError(
                f"No se pudo generar una respuesta con el modelo '{self.model}' en {self.host}. "
                f"Verifica que Ollama esté corriendo ('ollama serve') y que el modelo esté "
                f"descargado ('ollama pull {self.model}')."
            ) from exc
