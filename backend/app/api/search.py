"""Search API: vector search over MITRE entities by query (suffix/prefix)."""
from fastapi import APIRouter, HTTPException, Query

from app.db.mongo import MitreDBError, search_entities_by_embedding
from app.schemas.search import SearchResponse, SearchResultEntry
from app.services.embeddings import embed_text

router = APIRouter()

DEFAULT_TOP_K = 10


def _doc_to_entry(doc: dict) -> SearchResultEntry:
    """Map MongoDB vector search result doc to SearchResultEntry."""
    return SearchResultEntry(
        id=doc.get("id") or doc.get("_id", ""),
        type=doc.get("type"),
        name=doc.get("name"),
        description=doc.get("description"),
        x_mitre_shortname=doc.get("x_mitre_shortname"),
        score=float(doc.get("_score", 0.0)),
    )


@router.get("/", response_model=SearchResponse)
async def search_entities(
    q: str = Query(..., min_length=1, description="Search query (suffix/prefix) to match entities by embedding similarity"),
    top_k: int = Query(DEFAULT_TOP_K, ge=1, le=100, description="Maximum number of results to return (default 10)"),
) -> SearchResponse:
    """
    Search MITRE entities by semantic similarity.
    Embeds the query, runs vector search over entity embeddings, and returns the top-k matches.
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query string is required and must be non-empty")
    try:
        embedding = await embed_text(query)
        if not embedding:
            return SearchResponse(results=[])
        docs = await search_entities_by_embedding(embedding, top_k=top_k)
        results = [_doc_to_entry(d) for d in docs]
        return SearchResponse(results=results)
    except MitreDBError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database or vector search unavailable: {e!s}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Search unavailable: {e!s}",
        ) from e
