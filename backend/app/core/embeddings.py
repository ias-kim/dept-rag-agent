from collections.abc import Sequence
from typing import Any, Protocol

from app.core.config import Settings
from app.db.models import EMBEDDING_DIM


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, client: Any, model: str, batch_size: int = 64) -> None:
        self._client = client
        self._model = model
        self._batch_size = batch_size

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIEmbedder":
        from openai import OpenAI

        return cls(OpenAI(api_key=settings.openai_api_key), settings.embedding_model)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = list(texts[i : i + self._batch_size])
            response = self._client.embeddings.create(model=self._model, input=batch)
            vectors.extend(list(item.embedding) for item in response.data)
        for v in vectors:
            if len(v) != EMBEDDING_DIM:
                raise ValueError(f"embedding dimension {len(v)} != {EMBEDDING_DIM}")
        return vectors
