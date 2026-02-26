"""Neo4j storage for MITRE/STIX data. Syncs bundle objects as nodes and relationship objects as edges."""
import logging
import re

from neo4j import AsyncGraphDatabase

from app.config import settings
from app.schemas.mitre import MitreBundle, MitreObject

logger = logging.getLogger(__name__)

# Batch size for chunked deletes (CALL { ... } IN TRANSACTIONS)
_DELETE_BATCH_SIZE = 10_000
# Batch size for chunked creates (UNWIND per chunk)
_CREATE_BATCH_SIZE = 10_000
# Max rows returned by graph/UI queries to avoid supernodes overwhelming the UI
_GRAPH_QUERY_LIMIT = 500

# Allowlist for dynamic Cypher identifiers (labels/types cannot be parameterized)
_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9]+$")  # PascalCase / alphanumeric
_REL_TYPE_PATTERN = re.compile(r"^[A-Z0-9_]+$")  # UPPER_SNAKE


def _validate_label(label: str) -> str:
    """Allowlist: only alphanumeric label (PascalCase). Prevents Cypher injection."""
    if not label or not _LABEL_PATTERN.fullmatch(label):
        raise ValueError(f"Invalid Neo4j label (allowed: alphanumeric): {label!r}")
    return label


def _validate_relationship_type(rel_type: str) -> str:
    """Allowlist: only UPPER_SNAKE relationship type. Prevents Cypher injection."""
    if not rel_type or not _REL_TYPE_PATTERN.fullmatch(rel_type):
        raise ValueError(f"Invalid Neo4j relationship type (allowed: A-Z, 0-9, _): {rel_type!r}")
    return rel_type


def _chunked[T](items: list[T], size: int) -> list[list[T]]:
    """Split list into chunks of at most `size`."""
    return [items[i : i + size] for i in range(0, len(items), size)]

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


async def _ensure_stix_id_constraint(tx) -> None:
    """Create unique constraint on MitreEntity.stix_id so MERGE/MATCH use index (O(1)) instead of full scan."""
    await tx.run(
        "CREATE CONSTRAINT mitre_entity_stix_id_unique IF NOT EXISTS "
        "FOR (n:MitreEntity) REQUIRE n.stix_id IS UNIQUE"
    )


# Cypher: (a)-[r]->(b) where a or b has the given stix_id; returns raw a, r, b for graphviz. LIMIT caps supernodes.
_USES_INTO_CYPHER = """
MATCH (a)-[r]->(b)
WHERE b.stix_id = $stix_id OR a.stix_id = $stix_id
RETURN a, r, b
LIMIT $limit
"""


class Neo4jRepo:
    """Neo4j graph repository for MITRE bundles. Injected via app.state (see dependencies.get_neo4j_repo)."""

    def __init__(self, driver) -> None:
        self._driver = driver

    async def close(self) -> None:
        """Close the Neo4j driver. Call at app shutdown."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    async def store_mitre_bundle(self, content: MitreBundle) -> None:
        """
        Replace MITRE graph in Neo4j with the given bundle.
        - Non-relationship objects become nodes (labeled by type + MitreEntity).
        - Relationship objects become edges between nodes identified by source_ref/target_ref.
        """
        if self._driver is None:
            logger.error("Neo4j not available, skipping graph sync")
            return

        by_id: dict[str, MitreObject] = {obj.id: obj for obj in content.objects}
        nodes = [o for o in content.objects if o.type != "relationship"]
        relationships = [o for o in content.objects if o.type == "relationship"]

        nodes_by_label: dict[str, list[dict]] = {}
        for obj in nodes:
            label = _stix_type_to_label(obj.type)
            nodes_by_label.setdefault(label, []).append(_node_properties(obj))

        rel_rows: list[dict] = []
        for rel in relationships:
            if not rel.source_ref or not rel.target_ref or not rel.relationship_type:
                continue
            if rel.source_ref not in by_id or rel.target_ref not in by_id:
                continue
            rel_rows.append({
                "source_ref": rel.source_ref,
                "target_ref": rel.target_ref,
                "rel_type": _relationship_type_to_neo4j(rel.relationship_type),
                "rel_id": rel.id,
            })

        async with self._driver.session() as session:
            await session.execute_write(_clear_mitre_graph)
            for label, rows in nodes_by_label.items():
                for chunk in _chunked(rows, _CREATE_BATCH_SIZE):
                    await session.execute_write(_create_nodes_batch, label, chunk)
            rel_rows_by_type: dict[str, list[dict]] = {}
            for row in rel_rows:
                t = row["rel_type"].replace(" ", "_")
                rel_rows_by_type.setdefault(t, []).append(row)
            for rel_type, rows in rel_rows_by_type.items():
                for chunk in _chunked(rows, _CREATE_BATCH_SIZE):
                    await session.execute_write(_create_relationships_batch, rel_type, chunk)

        logger.info("Neo4j: stored %s nodes and %s relationships", len(nodes), len(rel_rows))

    async def get_uses_into_records(
        self,
        stix_id: str,
        limit: int | None = None,
    ) -> list[dict] | None:
        """
        Return list of records { "a": Node, "r": Relationship, "b": Node } for edges incident to the given stix_id.
        Returns None if driver unavailable.
        """
        if self._driver is None:
            return None
        capped_limit = min(limit or _GRAPH_QUERY_LIMIT, _GRAPH_QUERY_LIMIT)
        async with self._driver.session() as session:
            result = await session.run(
                _USES_INTO_CYPHER,
                stix_id=stix_id,
                limit=capped_limit,
            )
            records = [{"a": rec["a"], "r": rec["r"], "b": rec["b"]} async for rec in result]
        return records


async def init_neo4j() -> Neo4jRepo:
    """Connect to Neo4j and return Neo4jRepo. Store in app.state for dependency injection."""
    driver = None
    try:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
        await driver.verify_connectivity()
        async with driver.session() as session:
            await session.execute_write(_ensure_stix_id_constraint)
        logger.info("Neo4j connected")
        return Neo4jRepo(driver)
    except Exception as e:
        if driver is not None:
            try:
                await driver.close()
            except Exception:
                pass
        logger.error("Neo4j connection failed (MITRE graph storage will be skipped): %s", e)
        return Neo4jRepo(None)


async def close_neo4j(repo: Neo4jRepo) -> None:
    """Close Neo4j. Call at app shutdown with repo from app.state."""
    await repo.close()


async def _clear_mitre_graph(tx, batch_size: int = _DELETE_BATCH_SIZE) -> None:
    """Delete all MitreEntity nodes and their relationships in batched transactions."""
    # Stream nodes and delete in chunks to avoid a single huge transaction
    cypher = (
        "MATCH (n:MitreEntity) "
        "CALL { WITH n DETACH DELETE n RETURN 1 AS _ } IN TRANSACTIONS OF $batch_size ROWS"
    )
    await tx.run(cypher, batch_size=batch_size)


async def _create_nodes_batch(tx, label: str, rows: list[dict]) -> None:
    """Create/merge nodes in one transaction using UNWIND. Label allowlist-validated (PascalCase)."""
    if not rows:
        return
    label = _validate_label(label)
    cypher = (
        "UNWIND $rows AS row "
        f"MERGE (n:MitreEntity:{label} {{stix_id: row.stix_id}}) SET n += row"
    )
    await tx.run(cypher, rows=rows)


async def _create_relationships_batch(tx, rel_type: str, rows: list[dict]) -> None:
    """Merge relationships in one transaction using UNWIND. rel_type allowlist-validated (UPPER_SNAKE)."""
    if not rows:
        return
    rel_type = _validate_relationship_type(rel_type)
    cypher = (
        "UNWIND $rows AS row "
        "MATCH (a:MitreEntity {stix_id: row.source_ref}), (b:MitreEntity {stix_id: row.target_ref}) "
        f"MERGE (a)-[r:{rel_type} {{stix_id: row.rel_id}}]->(b)"
    )
    await tx.run(cypher, rows=rows)