"""Embedding service for MITRE entity name and description via LM Studio (nomic-embed)."""
from __future__ import annotations

from openai import AsyncOpenAI

from app.config import settings


def _name_description_text(name: str | None, description: str | None) -> str | None:
    """Build combined text for name+description; returns None if both empty."""
    name = (name or "").strip()
    description = (description or "").strip()
    if name and description:
        return f"name: {name}. description: {description}"
    if name:
        return name
    if description:
        return description
    return None


async def embed_text(text: str) -> list[float]:
    """
    Embed a single text string via LM Studio. Returns a list of floats (vector).
    Empty or whitespace-only text returns an empty list.
    """
    text = (text or "").strip()
    if not text:
        return []
    vectors = await embed_texts_batch([text])
    return vectors[0] if vectors else []


async def embed_name_and_description(name: str | None, description: str | None) -> list[float]:
    """
    Embed combined name and description for an entity via LM Studio.
    Uses "name: {name}. description: {description}" when both present;
    otherwise just the non-empty part. Returns [] if both are empty.
    """
    text = _name_description_text(name, description)
    if text is None:
        return []
    return await embed_text(text)


async def embed_texts_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of text strings via LM Studio (OpenAI-compatible embeddings API).
    Uses the nomic-embed model loaded in LM Studio. Returns list of vectors in same order.
    Empty strings in input yield empty list for that position.
    """
    if not texts:
        return []
    

    client = AsyncOpenAI(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
    )
    # Filter to non-empty and remember indices to map back
    indexed = [(i, t.strip()) for i, t in enumerate(texts) if (t or "").strip()]
    if not indexed:
        return [[] for _ in texts]
    indices, to_encode = zip(*indexed)
    response = await client.embeddings.create(
        input=list(to_encode),
        model=settings.embedding_model,
    )
    # response.data is in same order as input
    result = [[] for _ in texts]
    for k, idx in enumerate(indices):
        result[idx] = response.data[k].embedding
    return result
