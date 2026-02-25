"""Abstract service protocols for dependency injection and testing."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from langchain_core.messages import BaseMessage


@runtime_checkable
class EmbeddingService(Protocol):
    """Abstraction for embedding text into vectors."""

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single text; returns empty list for empty/whitespace input."""
        ...

    async def embed_texts_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts; returns list of vectors in same order."""
        ...


@runtime_checkable
class RetrievalService(Protocol):
    """Abstraction for RAG: retrieve relevant context for a query."""

    async def get_context(self, query: str, top_k: int = 5) -> str:
        """Return formatted context string for the query (empty on failure)."""
        ...


@runtime_checkable
class LLMService(Protocol):
    """Abstraction for chat LLM invocation."""

    async def invoke(self, messages: list[BaseMessage]) -> tuple[str, str]:
        """Invoke the model with messages; returns (reply_text, model_name)."""
        ...


@runtime_checkable
class ChatService(Protocol):
    """Abstraction for multi-turn chat with optional RAG."""

    async def chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> tuple[str, str]:
        """Run chat; returns (reply, model_name)."""
        ...
