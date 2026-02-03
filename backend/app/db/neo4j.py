"""Neo4j storage for MITRE/STIX data. Syncs bundle objects as nodes and relationship objects as edges."""
import logging
import os

from neo4j import AsyncGraphDatabase

from app.schemas.mitre import MitreBundle, MitreObject

logger = logging.getLogger(__name__)

_driver = None


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


def _node_properties(obj: MitreObject) -> dict:
    """Build a flat property dict for a node (scalars and list of strings only)."""
    d = obj.model_dump(mode="json")
    out = {}
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
    return out


async def init_neo4j() -> None:
    """Connect to Neo4j. Call once at app startup."""
    global _driver
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password123")
    try:
        _driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        await _driver.verify_connectivity()
        logger.info("Neo4j connected: %s", uri)
    except Exception as e:
        _driver = None
        logger.warning("Neo4j connection failed (MITRE graph storage will be skipped): %s", e)


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
        logger.debug("Neo4j not available, skipping graph sync")
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
            props = _node_properties(obj)
            await session.execute_write(_create_node, label, props)

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

    logger.info("Neo4j: stored %d nodes and %d relationships", len(nodes), len(relationships))


async def _clear_mitre_graph(tx) -> None:
    await tx.run("MATCH (n:MitreEntity) DETACH DELETE n")


async def _create_node(tx, label: str, props: dict) -> None:
    # Use MERGE on stix_id; then SET all properties. Label is from _stix_type_to_label (PascalCase).
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


# Cypher: node by stix_id and all adjacent nodes with their relationship
_ADJACENT_CYPHER = """
MATCH (n:MitreEntity {stix_id: $stix_id})
OPTIONAL MATCH (n)-[r]-(other:MitreEntity)
WHERE other.stix_id <> n.stix_id
RETURN properties(n) AS center,
       type(r) AS rel_type,
       properties(r) AS rel_props,
       properties(other) AS neighbor,
       startNode(r).stix_id = $stix_id AS from_center
"""


async def get_adjacent(stix_id: str) -> dict | None:
    """
    Return the node for stix_id and all adjacent nodes with their relationship.
    Shape: { "node": {...}, "adjacent": [ { "relationship": { "type", "stix_id", ... }, "direction": "outgoing"|"incoming", "node": {...} }, ... ] }
    Returns None if node not found or Neo4j unavailable.
    """
    driver = _get_driver()
    if driver is None:
        return None

    async with driver.session() as session:
        result = await session.run(_ADJACENT_CYPHER, stix_id=stix_id)
        records = await result.data()

    if not records:
        return None

    # First row has center (same for all rows); rows with no relationship have rel_type/rel_props/neighbor/from_center as None
    center = records[0].get("center")
    if not center:
        return None

    adjacent: list[dict] = []
    for rec in records:
        rel_type = rec.get("rel_type")
        if rel_type is None:
            continue
        rel_props = rec.get("rel_props") or {}
        neighbor = rec.get("neighbor")
        from_center = rec.get("from_center", False)
        if neighbor is None:
            continue
        adjacent.append({
            "relationship": {"type": rel_type, **rel_props},
            "direction": "outgoing" if from_center else "incoming",
            "node": neighbor,
        })

    return {"node": center, "adjacent": adjacent}


# Cypher: (a)-[r:USES]->(b) where b has the given stix_id; returns raw a, r, b for graphviz
#make it bidirectional
_USES_INTO_CYPHER = """
MATCH (a)-[r]->(b)
WHERE b.stix_id = $stix_id OR a.stix_id = $stix_id
RETURN a, r, b
"""
#make it bidirectional

async def get_uses_into_records(stix_id: str) -> list[dict] | None:
    """
    Return list of records { "a": Node, "r": Relationship, "b": Node } for (a)-[:USES]->(b) where b.stix_id = stix_id.
    For use with graphviz (raw Neo4j objects). Returns None if driver unavailable.
    """
    driver = _get_driver()
    if driver is None:
        return None

    async with driver.session() as session:
        result = await session.run(_USES_INTO_CYPHER, stix_id=stix_id)
        records = [{"a": rec["a"], "r": rec["r"], "b": rec["b"]} async for rec in result]
    return records