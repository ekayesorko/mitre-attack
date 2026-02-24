"""Search API: vector search over MITRE entities by query (suffix/prefix)."""
from fastapi import APIRouter, HTTPException, Query

from app.db.mongo import EntitySearchResult, MitreDBError, search_entities_by_embedding, search_entities_by_text
from app.schemas.search import SearchResponse, SearchResultEntry
from app.services.embeddings import embed_text

router = APIRouter()

DEFAULT_TOP_K = 10


def _result_to_entry(doc: EntitySearchResult) -> SearchResultEntry:
    """Map EntitySearchResult to SearchResultEntry."""
    return SearchResultEntry(
        id=doc.id,
        type=doc.type,
        name=doc.name,
        x_mitre_shortname=doc.x_mitre_shortname,
        score=doc.score,
    )


def _merge_vector_and_text(
    vector_docs: list[EntitySearchResult],
    text_docs: list[EntitySearchResult],
    top_k: int,
) -> list[EntitySearchResult]:
    """Put text (literal) matches first, then fill with vector-only results up to top_k."""
    seen_ids: set[str] = set()
    merged: list[EntitySearchResult] = []
    for d in text_docs:
        if d.id and d.id not in seen_ids:
            seen_ids.add(d.id)
            merged.append(d)
            if len(merged) >= top_k:
                return merged
    for d in vector_docs:
        if d.id and d.id not in seen_ids:
            seen_ids.add(d.id)
            merged.append(d)
            if len(merged) >= top_k:
                return merged
    return merged


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
        text_docs = await search_entities_by_text(query, top_k=top_k)
        if not embedding:
            docs = text_docs
        else:
            vector_docs = await search_entities_by_embedding(embedding, top_k=top_k)
            docs = _merge_vector_and_text(vector_docs, text_docs, top_k)
        results = [_result_to_entry(d) for d in docs]
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
