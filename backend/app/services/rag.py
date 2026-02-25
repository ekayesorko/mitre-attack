"""RAG: retrieve relevant MITRE entities from MongoDB (pre-embedded) for chat context."""
from __future__ import annotations

import logging

from app.db.mongo import MitreDBError, search_entities_by_embedding
from app.services.protocols import EmbeddingService

logger = logging.getLogger(__name__)


def _format_entity(d: dict) -> str:
    """Format a single entity for context (name, type, description)."""
    parts = []
    if d.get("name"):
        parts.append(f"Name: {d['name']}")
    if d.get("type"):
        parts.append(f"Type: {d['type']}")
    if d.get("id"):
        parts.append(f"ID: {d['id']}")
    if d.get("x_mitre_shortname"):
        parts.append(f"Short name: {d['x_mitre_shortname']}")
    if d.get("description"):
        parts.append(f"Description: {d['description']}")
    return "\n".join(parts) if parts else ""


def format_entities_as_context(
    entities: list[dict], separator: str = "\n\n---\n\n"
) -> str:
    """Turn a list of entity dicts into one context string."""
    if not entities:
        return ""
    return separator.join(_format_entity(e) for e in entities)


class RAGRetrievalService:
    """RAG retrieval using an embedding service and MongoDB vector search."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        *,
        default_top_k: int = 5,
    ) -> None:
        self._embedding = embedding_service
        self._default_top_k = default_top_k

    async def get_context(self, query: str, top_k: int | None = None) -> str:
        k = top_k if top_k is not None else self._default_top_k
        query = (query or "").strip()
        if not query:
            logger.debug("RAG: empty query, no context")
            return ""
        try:
            embedding = await self._embedding.embed_text(query)
            if not embedding:
                logger.warning("RAG: embedding service returned empty vector (check EMBEDDING_MODEL and Ollama)")
                return ""
            entities = await search_entities_by_embedding(embedding, top_k=k)
            context = format_entities_as_context(entities)
            if not context:
                logger.warning(
                    "RAG: no entities found (vector index ready? mitre_entities populated with embeddings?)"
                )
            return context
        except MitreDBError as e:
            logger.warning("RAG: MongoDB/vector search failed: %s", e)
            return ""
        except Exception as e:
            logger.warning("RAG: embedding or retrieval failed: %s", e)
            return ""
