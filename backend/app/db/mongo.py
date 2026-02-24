"""MongoDB access for MITRE documents. Three collections:

- current_schema: single document with current x_mitre_version
- mitre_entities: latest MITRE entities as individual documents (_id = entity id), with optional embedding (name+description)
- mitre_documents: whole MITRE bundle per version (_id = x_mitre_version)

Vector search uses MongoDB Atlas $vectorSearch (requires a vector search index on mitre_entities.embedding).
Set VECTOR_SEARCH_INDEX_NAME to match your Atlas index (default: mitre_entities_vector).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.config import settings
from app.schemas.mitre import MitreBundle, MitreMetadata, MitreObject, MitreVersionInfo
from app.services.embeddings import _name_description_text, embed_texts_batch

logger = logging.getLogger(__name__)


class MitreDBError(Exception):
    """Raised when a MongoDB operation fails (connection, timeout, or write error)."""
    pass


class DuplicateVersionError(MitreDBError):
    """Raised when inserting a MITRE document for a version that already exists."""
    pass


@dataclass(frozen=True)
class EntitySearchResult:
    """A single entity hit from vector or text search (no embedding)."""
    id: str
    type: str | None
    name: str | None
    x_mitre_shortname: str | None
    score: float


CURRENT_DOC_ID = "current"
DATABASE_NAME = "mitre_db"

# collection names
COLLECTION_CURRENT_SCHEMA = "current_schema"
COLLECTION_LATEST_ENTITIES = "mitre_entities"
COLLECTION_DOCUMENTS = "mitre_documents"

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase[dict[str, Any]] | None = None


def _get_db() -> AsyncIOMotorDatabase[dict[str, Any]]:
    """Return database instance; call after init_db."""
    global _db
    if _db is None:
        raise RuntimeError("DB not initialized. Call init_db() first.")
    return _db


async def init_db() -> None:
    """Connect to MongoDB and ensure indexes. Call once at app startup."""
    global _client, _db
    try:
        _client = AsyncIOMotorClient[dict[str, Any]](settings.mongodb_uri, serverSelectionTimeoutMS=5000)
        await _client.admin.command("ping")
        _db = _client[DATABASE_NAME]

        # current_schema: single doc, no index needed beyond _id
        # mitre_entities: index by type for listing/filtering
        await _db[COLLECTION_LATEST_ENTITIES].create_index([("type", 1)])
        # mitre_documents: keyed by version (_id), no extra index needed
        await _db[COLLECTION_DOCUMENTS].create_index([("_id", 1)])

        # Vector search index (Atlas only; createSearchIndexes only works on Atlas)
        await _ensure_vector_search_index()
    except PyMongoError as e:
        _client = None
        _db = None
        raise MitreDBError(f"MongoDB connection or init failed: {e}") from e


async def close_db() -> None:
    """Close MongoDB connection. Call at app shutdown."""
    global _client, _db
    try:
        if _client is not None:
            _client.close()
            _client = None
        _db = None
    except Exception:
        _client = None
        _db = None
        raise


async def get_mitre_version() -> str | None:
    """Return current x_mitre_version or None if none set."""
    try:
        collection = _get_db()[COLLECTION_CURRENT_SCHEMA]
        doc = await collection.find_one({"_id": CURRENT_DOC_ID})
        if doc is None:
            return None
        version: str | None = doc.get("x_mitre_version")
        return version
    except PyMongoError as e:
        raise MitreDBError(f"Failed to get MITRE version: {e}") from e


async def list_mitre_versions() -> list[MitreVersionInfo]:
    """
    Return all available MITRE versions from mitre_documents.
    Each item has x_mitre_version and metadata; newest first by last_modified.
    """
    try:
        collection = _get_db()[COLLECTION_DOCUMENTS]
        cursor = collection.find(
            {},
            {"_id": 1, "metadata": 1},
        ).sort("metadata.last_modified", -1)
        docs = await cursor.to_list(length=None)
        result: list[MitreVersionInfo] = []
        for doc in docs:
            mid: str = doc["_id"]
            meta = doc.get("metadata") or {}
            result.append(
                MitreVersionInfo(
                    x_mitre_version=mid,
                    metadata=MitreMetadata(
                        x_mitre_version=meta.get("x_mitre_version", mid),
                        last_modified=meta.get("last_modified", ""),
                        size=int(meta.get("size", 0)),
                        type=meta.get("type", "application/json"),
                    ),
                )
            )
        return result
    except PyMongoError as e:
        raise MitreDBError(f"Failed to list MITRE versions: {e}") from e


async def _entity_docs_with_embeddings(content: MitreBundle) -> list[dict[str, Any]]:
    """
    Build entity documents with embedding field for name+description.
    Uses LM Studio (nomic-embed) via OpenAI-compatible embeddings API.
    """
    entity_docs: list[dict[str, Any]] = []
    docs_with_text: list[tuple[dict[str, Any], str]] = []
    for obj in content.objects:
        doc: dict[str, Any] = {"_id": obj.id, **obj.model_dump(mode="json")}
        entity_docs.append(doc)
        text = _name_description_text(obj.name, obj.description)
        if text:
            docs_with_text.append((doc, text))
    if docs_with_text:
        texts = [t for _, t in docs_with_text]
        embeddings = await embed_texts_batch(texts)
        for (doc, _), vec in zip(docs_with_text, embeddings):
            doc["embedding"] = vec
    return entity_docs


async def get_mitre_content() -> tuple[MitreBundle, MitreMetadata] | None:
    """Return (content, metadata) for current version, or None."""
    try:
        version = await get_mitre_version()
        if version is None:
            return None
        collection = _get_db()[COLLECTION_DOCUMENTS]
        doc = await collection.find_one({"_id": version})
        if doc is None:
            return None
        metadata = MitreMetadata(
            x_mitre_version=doc["metadata"]["x_mitre_version"],
            last_modified=doc["metadata"]["last_modified"],
            size=doc["metadata"]["size"],
            type=doc["metadata"]["type"],
        )
        content = MitreBundle(
            type="bundle",
            id=doc.get("bundle_id"),
            spec_version=doc.get("spec_version", "2.1"),
            objects=[MitreObject.model_validate(o) for o in doc["objects"]],
        )
        return (content, metadata)
    except MitreDBError:
        raise
    except PyMongoError as e:
        raise MitreDBError(f"Failed to get MITRE content: {e}") from e


async def get_mitre_content_by_version(x_mitre_version: str) -> tuple[MitreBundle, MitreMetadata] | None:
    """Return (content, metadata) for the given version, or None if not found."""
    try:
        collection = _get_db()[COLLECTION_DOCUMENTS]
        doc = await collection.find_one({"_id": x_mitre_version})
        if doc is None:
            return None
        metadata = MitreMetadata(
            x_mitre_version=doc["metadata"]["x_mitre_version"],
            last_modified=doc["metadata"]["last_modified"],
            size=doc["metadata"]["size"],
            type=doc["metadata"]["type"],
        )
        content = MitreBundle(
            type="bundle",
            id=doc.get("bundle_id"),
            spec_version=doc.get("spec_version", "2.1"),
            objects=[MitreObject.model_validate(o) for o in doc["objects"]],
        )
        return (content, metadata)
    except MitreDBError:
        raise
    except PyMongoError as e:
        raise MitreDBError(f"Failed to get MITRE content: {e}") from e


# Atlas vector search index name. Create in Atlas UI (Search → Create Index → JSON editor).
# Example index definition for collection "mitre_entities":
#   { "fields": [ { "type": "vector", "path": "embedding", "numDimensions": 768, "similarity": "cosine" } ] }
# nomic-embed-text uses 768 dimensions.
VECTOR_EMBEDDING_DIMENSIONS = 768


async def _ensure_vector_search_index() -> None:
    """
    Create the vector search index on mitre_entities if missing.
    Only succeeds on MongoDB Atlas (createSearchIndexes is Atlas-only).
    """
    try:
        res = await _get_db().command(
            {
                "createSearchIndexes": COLLECTION_LATEST_ENTITIES,
                "indexes": [
                    {
                        "name": settings.vector_search_index_name,
                        "type": "vectorSearch",
                        "definition": {
                            "fields": [
                                {
                                    "type": "vector",
                                    "path": "embedding",
                                    "numDimensions": VECTOR_EMBEDDING_DIMENSIONS,
                                    "similarity": "cosine",
                                }
                            ]
                        },
                    }
                ],
            }
        )
        if res.get("ok") == 1 and res.get("indexesCreated"):
            logger.info("Vector search index created:")
        elif res.get("ok") == 1:
            logger.info("Vector search index already exists or creation skipped")
    except PyMongoError as e:
        logger.error("Could not create vector search index", e)


def _doc_to_entity_search_result(doc: dict[str, Any]) -> EntitySearchResult:
    """Map a MongoDB search result document to EntitySearchResult."""
    eid: str = doc.get("id") or doc.get("_id") or ""
    return EntitySearchResult(
        id=eid,
        type=doc.get("type"),
        name=doc.get("name"),
        x_mitre_shortname=doc.get("x_mitre_shortname"),
        score=float(doc.get("_score", 0.0)),
    )


async def search_entities_by_embedding(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[EntitySearchResult]:
    """
    Return top_k MITRE entities most similar to query_embedding using MongoDB Atlas $vectorSearch.
    Requires a vector search index on the collection (path: embedding, cosine similarity).
    """
    if not query_embedding or top_k <= 0:
        return []
    num_candidates = max(100, top_k * 20)  # Atlas recommendation for ANN recall
    # Fetch extra so that after excluding relationships we still have top_k (filter can't use unindexed 'type')
    search_limit = max(top_k * 10, 50)
    pipeline = [
        {
            "$vectorSearch": {
                "index": settings.vector_search_index_name,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": num_candidates,
                "limit": search_limit,
            }
        },
        {"$match": {"type": {"$ne": "relationship"}}},
        {"$limit": top_k},
        {
            "$project": {
                "type": 1,
                "name": 1,
                "id": 1,
                "x_mitre_shortname": 1,
                "_score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    try:
        collection = _get_db()[COLLECTION_LATEST_ENTITIES]
        cursor = collection.aggregate(pipeline)
        docs = await cursor.to_list(length=top_k)
    except PyMongoError as e:
        raise MitreDBError(
            f"Vector search failed (is Atlas vector index '{settings.vector_search_index_name}' defined?): {e}"
        ) from e
    return [_doc_to_entity_search_result(d) for d in docs]


async def search_entities_by_text(query: str, top_k: int = 10) -> list[EntitySearchResult]:
    """
    Match query as case-insensitive substring in name only.
    Excludes relationships. Returns same shape as vector search (id, type, name, x_mitre_shortname, score=1.0).
    """
    query = (query or "").strip()
    if not query or top_k <= 0:
        return []
    try:
        collection = _get_db()[COLLECTION_LATEST_ENTITIES]
        regex: dict[str, Any] = {"$regex": query, "$options": "i"}
        cursor = collection.find(
            {
                "type": {"$ne": "relationship"},
                "name": regex,
            },
            {"_id": 1, "id": 1, "type": 1, "name": 1, "x_mitre_shortname": 1},
        ).limit(top_k)
        docs = await cursor.to_list(length=top_k)
        return [_doc_to_entity_search_result({**d, "_score": 1.0}) for d in docs]
    except PyMongoError as e:
        raise MitreDBError(f"Text search failed: {e}") from e


async def put_mitre_document(
    x_mitre_version: str,
    content: MitreBundle,
    metadata: MitreMetadata,
) -> None:
    """
    Store MITRE data in three collections:
    - current_schema: set current version
    - mitre_entities: replace with latest entities (one doc per entity, _id = entity id)
    - mitre_documents: store whole bundle for this version (_id = version)
    """
    db = _get_db()
    docs_collection = db[COLLECTION_DOCUMENTS]
    entities_collection = db[COLLECTION_LATEST_ENTITIES]
    schema_collection = db[COLLECTION_CURRENT_SCHEMA]

    try:
        # 1. Store whole MITRE document by version
        doc = {
            "_id": x_mitre_version,
            "metadata": metadata.model_dump(mode="json"),
            "spec_version": content.spec_version,
            "bundle_id": content.id,
            "objects": [o.model_dump(mode="json") for o in content.objects],
        }
        await docs_collection.replace_one({"_id": x_mitre_version}, doc, upsert=True)

        # 2. Replace latest entities: clear and insert current version's entities (each with _id = entity id, plus embedding for name+description)
        await entities_collection.delete_many({})
        entity_docs = await _entity_docs_with_embeddings(content)
        if entity_docs:
            await entities_collection.insert_many(entity_docs)

        # 3. Set current schema (current version)
        await schema_collection.replace_one(
            {"_id": CURRENT_DOC_ID},
            {"_id": CURRENT_DOC_ID, "x_mitre_version": x_mitre_version},
            upsert=True,
        )
    except PyMongoError as e:
        raise MitreDBError(f"Failed to store MITRE document: {e}") from e


async def insert_mitre_document(
    x_mitre_version: str,
    content: MitreBundle,
    metadata: MitreMetadata,
) -> None:
    db = _get_db()
    docs_collection = db[COLLECTION_DOCUMENTS]
    entities_collection = db[COLLECTION_LATEST_ENTITIES]
    schema_collection = db[COLLECTION_CURRENT_SCHEMA]

    try:
        doc = {
            "_id": x_mitre_version,
            "metadata": metadata.model_dump(mode="json"),
            "spec_version": content.spec_version,
            "bundle_id": content.id,
            "objects": [o.model_dump(mode="json") for o in content.objects],
        }
        await docs_collection.insert_one(doc)
    except DuplicateKeyError as e:
        raise DuplicateVersionError(
            f"MITRE version '{x_mitre_version}' already exists"
        ) from e
    except PyMongoError as e:
        raise MitreDBError(f"Failed to store MITRE document: {e}") from e

    try:
        # 2. Replace latest entities with this version's entities (with name+description embeddings)
        await entities_collection.delete_many({})
        entity_docs = await _entity_docs_with_embeddings(content)
        if entity_docs:
            await entities_collection.insert_many(entity_docs)

        # 3. Set current schema to this new version
        await schema_collection.replace_one(
            {"_id": CURRENT_DOC_ID},
            {"_id": CURRENT_DOC_ID, "x_mitre_version": x_mitre_version},
            upsert=True,
        )
    except PyMongoError as e:
        raise MitreDBError(f"Failed to store MITRE document: {e}") from e
