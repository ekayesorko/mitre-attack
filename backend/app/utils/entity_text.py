"""Build combined text from entity name and description for embedding or display."""
from __future__ import annotations


def entity_text_for_embedding(name: str | None, description: str | None) -> str | None:
    """
    Build combined text for name+description for embedding.
    Returns None if both are empty.
    """
    name = (name or "").strip()
    description = (description or "").strip()
    if name and description:
        return f"name: {name}. description: {description}"
    if name:
        return name
    if description:
        return description
    return None
