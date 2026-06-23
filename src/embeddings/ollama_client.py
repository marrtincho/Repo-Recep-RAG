"""
Cliente de embeddings sobre Ollama.

Envoltorio fino sobre la librería oficial `ollama`. Aísla al resto del
sistema de los detalles de esa librería: si cambia su API o se sustituye por
otro cliente, solo este módulo debería tocarse.
"""

from __future__ import annotations

import ollama


class EmbeddingError(Exception):
    """Error al generar embeddings vía Ollama (servidor no disponible, modelo no descargado, etc.)."""


class OllamaEmbeddingClient:
    """Genera embeddings usando un modelo servido por Ollama (p. ej. nomic-embed-text)."""

    def __init__(self, model: str, host: str) -> None:
        self.model = model
        self.host = host
        self._client = ollama.Client(host=host)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Genera un embedding por cada texto de `texts`, en el mismo orden.

        Usa la API de embedding en lote del cliente si está disponible
        (`Client.embed`, soportada desde ollama-python 0.3+), y recurre a
        llamadas individuales con `Client.embeddings` si no lo está, para
        mantener compatibilidad con versiones anteriores del cliente.
        """
        if not texts:
            return []
        try:
            if hasattr(self._client, "embed"):
                response = self._client.embed(model=self.model, input=texts)
                return [list(vector) for vector in response["embeddings"]]
            return [self._embed_one(text) for text in texts]
        except EmbeddingError:
            raise
        except Exception as exc:  # la librería ollama puede lanzar varios tipos según el fallo
            raise EmbeddingError(
                f"No se pudo generar embeddings con el modelo '{self.model}' en {self.host}. "
                f"Verifica que Ollama esté corriendo ('ollama serve') y que el modelo esté "
                f"descargado ('ollama pull {self.model}')."
            ) from exc

    def _embed_one(self, text: str) -> list[float]:
        response = self._client.embeddings(model=self.model, prompt=text)
        return list(response["embedding"])
