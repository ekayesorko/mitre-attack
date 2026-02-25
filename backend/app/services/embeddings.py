"""Embedding service for MITRE entity name and description via LM Studio (nomic-embed)."""
from __future__ import annotations

from openai import AsyncOpenAI

from app.config import settings


class EmbeddingService:
    """LM Studio (OpenAI-compatible) embedding implementation."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._base_url = base_url or settings.lm_studio_base_url
        self._api_key = api_key or settings.lm_studio_api_key
        self._model = model or settings.embedding_model
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
        )

    async def embed_text(self, text: str) -> list[float]:
        text = (text or "").strip()
        if not text:
            return []
        vectors = await self.embed_texts_batch([text])
        return vectors[0] if vectors else []

    async def embed_texts_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in one API call. Returns one vector per input; empty/whitespace inputs get []."""
        indices, to_encode = [], []
        for i, t in enumerate(texts):
            indices.append(i)
            to_encode.append(t.strip())
        response = await self._client.embeddings.create(
            input=to_encode,
            model=self._model,
        )
        return [response.data[i].embedding for i in indices]
