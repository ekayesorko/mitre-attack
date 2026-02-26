"""Graph API: Neo4j queries by STIX id (e.g. adjacent nodes, SVG graph)."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from graphviz import Digraph

from app.dependencies import get_neo4j_repo
from app.db.neo4j import Neo4jRepo
from app.schemas.db import GraphRecord

router = APIRouter()


def _node_id(node) -> str:
    """Stable, graphviz-safe id: prefer stix_id so labels never show internal ids like '4'."""
    try:
        sid = node.get("stix_id") if node else None
        if sid:
            return str(sid).replace("-", "_")
    except Exception:
        pass
    return str(getattr(node, "element_id", None) or getattr(node, "id", id(node))).replace("-", "_")


def _node_label(node) -> str:
    """Display label for a Neo4j Node (name or stix_id only)."""
    if node is None:
        return "Unknown"
    try:
        name = node.get("name")
        if name is not None and str(name).strip():
            return str(name)
        sid = node.get("stix_id")
        if sid is not None and str(sid).strip():
            return str(sid)
    except Exception:
        pass
    return "Unknown"


def _build_svg_bytes(records: list[GraphRecord]) -> bytes:
    """Build a Digraph from (a)-[r:USES]->(b) records and return SVG bytes."""
    dot = Digraph("MITRE", format="svg")
    dot.attr(rankdir="LR", splines="true", nodesep="0.6", ranksep="1.2")
    dot.attr("edge", fontsize="10", labeldistance="1.5")
    seen_nodes: set[str] = set()
    for rec in records:
        a, b, r = rec.a, rec.b, rec.r
        if a is None or b is None or r is None:
            continue
        a_id = _node_id(a)
        b_id = _node_id(b)
        if a_id not in seen_nodes:
            dot.node(a_id, _node_label(a))
            seen_nodes.add(a_id)
        if b_id not in seen_nodes:
            dot.node(b_id, _node_label(b))
            seen_nodes.add(b_id)
        rel_label = getattr(r, "type", "USES")
        dot.edge(a_id, b_id, label=rel_label)
    return dot.pipe(format="svg")


@router.get("/svg")
async def get_svg_endpoint(
    stix_id: str,
    neo4j_repo: Neo4jRepo = Depends(get_neo4j_repo),
) -> Response:
    """
    Return an SVG graph of (a)-[:USES]->(b) where b has the given stix_id.
    Nodes are entities that USE the given technique; the center node is the technique.
    """
    records = await neo4j_repo.get_uses_into_records(stix_id)
    if records is None:
        raise HTTPException(
            status_code=503,
            detail="Neo4j is unavailable.",
        )
    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No USES relationships found for stix_id '{stix_id}'.",
        )
    svg_bytes = _build_svg_bytes(records)
    return Response(content=svg_bytes, media_type="image/svg+xml")
