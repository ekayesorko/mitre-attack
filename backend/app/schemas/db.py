"""Strict dataclass types for DB layer (no dict in public API)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.mitre import MitreMetadata, MitreObject


@dataclass(frozen=True)
class EntitySearchResult:
    """A single entity hit from vector or text search (no embedding)."""

    id: str
    type: str | None
    name: str | None
    description: str | None
    x_mitre_shortname: str | None
    score: float


@dataclass
class MitreEntityDoc:
    """Entity document for MongoDB mitre_entities: one STIX object plus optional embedding."""

    entity: MitreObject
    embedding: list[float] | None = None

    def to_mongo_doc(self) -> dict[str, Any]:
        """BSON-safe dict for insert_many (includes _id and optional embedding)."""
        doc: dict[str, Any] = {"_id": self.entity.id, **self.entity.model_dump(mode="json")}
        if self.embedding is not None:
            doc["embedding"] = self.embedding
        return doc


@dataclass(frozen=True)
class MitreVersionEntry:
    """Single version row from list_mitre_versions (DB layer)."""

    x_mitre_version: str
    metadata: MitreMetadata


# Neo4j driver returns Record with Node and Relationship; use Any to avoid driver dependency in types
@dataclass(frozen=True)
class GraphRecord:
    """One (source node, relationship, target node) from a graph query."""

    a: Any  # neo4j.graph.Node
    r: Any  # neo4j.graph.Relationship
    b: Any  # neo4j.graph.Node

    def to_dict(self) -> dict[str, Any]:
        """Legacy shape for code that expects rec['a'], rec['r'], rec['b']."""
        return {"a": self.a, "r": self.r, "b": self.b}
