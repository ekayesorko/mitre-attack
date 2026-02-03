"""RAG: retrieve relevant MITRE entities from MongoDB (pre-embedded) for chat context."""
from __future__ import annotations

from app.db.mongo import MitreDBError, search_entities_by_embedding
from app.services.embeddings import embed_text


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


def format_entities_as_context(entities: list[dict], separator: str = "\n\n---\n\n") -> str:
    """Turn a list of entity dicts (from search_entities_by_embedding) into one context string."""
    if not entities:
        return ""
    return separator.join(_format_entity(e) for e in entities)


async def get_relevant_mitre_context(query: str, top_k: int = 5) -> str:
    """
    Embed the query, retrieve top_k similar MITRE entities from MongoDB, and return
    formatted context string for RAG. Uses pre-computed entity embeddings.
    On any failure (embedding or vector search), returns empty string so chat can proceed without RAG.
    """
    query = (query or "").strip()
    if not query:
        return ""
    try:
        embedding = await embed_text(query)
        if not embedding:
            return ""
        entities = await search_entities_by_embedding(embedding, top_k=top_k)
        return format_entities_as_context(entities)
    except MitreDBError as e:
        print("RAG: MongoDB/vector search failed, continuing without context:", e)
        return ""
    except Exception as e:
        print("RAG: embedding or retrieval failed, continuing without context:", e)
        return ""
