"""Neo4j storage for MITRE/STIX data. Syncs bundle objects as nodes and relationship objects as edges."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Union

from neo4j import AsyncGraphDatabase
from neo4j.graph import Node, Relationship

from app.config import settings
from app.schemas.mitre import MitreBundle, MitreObject

# Typed node property values for Neo4j (scalars and list of strings only).
NodePropValue = Union[str, int, float, bool, list[str]]


@dataclass(frozen=True)
class NodeProperties:
    """Flat properties for a Neo4j node. Must include 'stix_id'. Used for MERGE/SET."""

    data: dict[str, NodePropValue]

    def to_cypher_dict(self) -> dict[str, NodePropValue]:
        return dict(self.data)


@dataclass
class UsesRecord:
    """Single (a)-[r]->(b) record from a USES-style query. For use with graphviz."""

    a: Node
    r: Relationship
    b: Node

_driver = None
logger = logging.getLogger(__name__)

def _stix_type_to_label(stix_type: str) -> str:
    """Convert STIX type to a valid Neo4j label (PascalCase). E.g. 'attack-pattern' -> 'AttackPattern'."""
    if not stix_type:
        return "StixObject"
    parts = stix_type.replace("-", " ").split()
    return "".join(p.capitalize() for p in parts)


def _relationship_type_to_neo4j(rel_type: str) -> str:
    """Convert STIX relationship_type to valid Neo4j relationship type (UPPER_SNAKE)."""
    if not rel_type:
        return "RELATED_TO"
    return rel_type.upper().replace("-", "_")


def _node_properties(obj: MitreObject) -> NodeProperties:
    """Build a flat property container for a node (scalars and list of strings only)."""
    d = obj.model_dump(mode="json")
    out: dict[str, NodePropValue] = {}
    for k, v in d.items():
        if k in ("relationship_type", "source_ref", "target_ref", "start_time", "stop_time"):
            continue
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            out[k] = v
        elif isinstance(v, list) and not v:
            continue
        # Skip nested objects (external_references, kill_chain_phases, etc.) for simplicity
    out["stix_id"] = d["id"]
    return NodeProperties(data=out)


async def init_neo4j() -> None:
    """Connect to Neo4j. Call once at app startup."""
    global _driver
    try:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
        await _driver.verify_connectivity()
        logger.info("Neo4j connected:")
    except Exception as e:
        _driver = None
        logger.error("Neo4j connection failed (MITRE graph storage will be skipped):", e)


async def close_neo4j() -> None:
    """Close Neo4j driver. Call at app shutdown."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
        logger.info("Neo4j connection closed")


def _get_driver():
    if _driver is None:
        return None
    return _driver


async def store_mitre_bundle(content: MitreBundle) -> None:
    """
    Replace MITRE graph in Neo4j with the given bundle.
    - Non-relationship objects become nodes (labeled by type + MitreEntity).
    - Relationship objects become edges between nodes identified by source_ref/target_ref.
    """
    driver = _get_driver()
    if driver is None:
        logger.error("Neo4j not available, skipping graph sync")
        return

    # Id -> object for lookups
    by_id: dict[str, MitreObject] = {obj.id: obj for obj in content.objects}

    nodes = [o for o in content.objects if o.type != "relationship"]
    relationships = [o for o in content.objects if o.type == "relationship"]

    async with driver.session() as session:
        # Clear existing MITRE nodes (and their relationships)
        await session.execute_write(_clear_mitre_graph)

        # Create nodes
        for obj in nodes:
            label = _stix_type_to_label(obj.type)
            node_props = _node_properties(obj)
            await session.execute_write(_create_node, label, node_props)

        # Create relationships
        for rel in relationships:
            if not rel.source_ref or not rel.target_ref or not rel.relationship_type:
                continue
            if rel.source_ref not in by_id or rel.target_ref not in by_id:
                continue
            rel_type = _relationship_type_to_neo4j(rel.relationship_type)
            await session.execute_write(
                _create_relationship,
                rel.source_ref,
                rel.target_ref,
                rel_type,
                rel.id,
            )

    logger.info("Neo4j: stored %s nodes and %s relationships", len(nodes), len(relationships))


async def _clear_mitre_graph(tx) -> None:
    await tx.run("MATCH (n:MitreEntity) DETACH DELETE n")


async def _create_node(tx, label: str, node_props: NodeProperties) -> None:
    # Use MERGE on stix_id; then SET all properties. Label is from _stix_type_to_label (PascalCase).
    props = node_props.to_cypher_dict()
    cypher = f"MERGE (n:MitreEntity:{label} {{stix_id: $stix_id}}) SET n += $props"
    await tx.run(cypher, stix_id=props["stix_id"], props=props)


async def _create_relationship(tx, source_ref: str, target_ref: str, rel_type: str, rel_id: str) -> None:
    # Sanitize rel_type for Cypher (no backticks in type name if already safe)
    safe_type = rel_type.replace(" ", "_")
    cypher = (
        "MATCH (a:MitreEntity {stix_id: $source_ref}), (b:MitreEntity {stix_id: $target_ref}) "
        f"CREATE (a)-[r:{safe_type} {{stix_id: $rel_id}}]->(b)"
    )
    await tx.run(cypher, source_ref=source_ref, target_ref=target_ref, rel_id=rel_id)


# Cypher: (a)-[r:USES]->(b) where b has the given stix_id; returns raw a, r, b for graphviz
_USES_INTO_CYPHER = """
MATCH (a)-[r]->(b)
WHERE b.stix_id = $stix_id OR a.stix_id = $stix_id
RETURN a, r, b
"""

async def get_uses_into_records(stix_id: str) -> list[UsesRecord] | None:
    """
    Return list of (a)-[r]->(b) records for queries where b.stix_id = stix_id or a.stix_id = stix_id.
    For use with graphviz (raw Neo4j objects). Returns None if driver unavailable.
    """
    driver = _get_driver()
    if driver is None:
        return None

    async with driver.session() as session:
        result = await session.run(_USES_INTO_CYPHER, stix_id=stix_id)
        records = [
            UsesRecord(a=rec["a"], r=rec["r"], b=rec["b"]) async for rec in result
        ]
    return records