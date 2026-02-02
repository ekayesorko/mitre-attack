"""Search API request/response schemas (vector search over entity embeddings)."""
from pydantic import BaseModel, Field


class SearchResultEntry(BaseModel):
    """A single entity hit from vector search (no embedding)."""

    id: str = Field(..., description="STIX entity ID")
    type: str | None = Field(None, description="Entity type (e.g. attack-pattern, course-of-action)")
    name: str | None = Field(None, description="Entity name")
    x_mitre_shortname: str | None = Field(None, description="MITRE short name if present")
    score: float = Field(..., description="Similarity score from vector search (higher = more similar)")


class SearchResponse(BaseModel):
    """Top-k entity search results by embedding similarity."""

    results: list[SearchResultEntry] = Field(
        ...,
        description="Ordered list of top matching entities (up to top_k)",
    )
