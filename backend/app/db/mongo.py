"""MongoDB access for MITRE documents. Three collections:

- current_schema: single document with current x_mitre_version
- mitre_entities: latest MITRE entities as individual documents (_id = entity id), with optional embedding (name+description)
- mitre_documents: whole MITRE bundle per version (_id = x_mitre_version)

Vector search uses MongoDB Atlas $vectorSearch (requires a vector search index on mitre_entities.embedding).
Set VECTOR_SEARCH_INDEX_NAME to match your Atlas index (default: mitre_entities_vector).
"""
import logging
import os

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, PyMongoError

logger = logging.getLogger(__name__)

from app.db.neo4j import store_mitre_bundle
from app.schemas.mitre import MitreBundle, MitreMetadata, MitreObject
from app.services.embeddings import _name_description_text, embed_texts_batch


class MitreDBError(Exception):
    """Raised when a MongoDB operation fails (connection, timeout, or write error)."""
    pass


class DuplicateVersionError(MitreDBError):
    """Raised when inserting a MITRE document for a version that already exists."""
    pass

CURRENT_DOC_ID = "current"
DATABASE_NAME = "mitre_db"

# collection names
COLLECTION_CURRENT_SCHEMA = "current_schema"
COLLECTION_LATEST_ENTITIES = "mitre_entities"
COLLECTION_DOCUMENTS = "mitre_documents"

_client: AsyncIOMotorClient | None = None
_db = None


def _get_db():
    """Return database instance; call after init_db."""
    global _db
    if _db is None:
        raise RuntimeError("DB not initialized. Call init_db() first.")
    return _db


async def init_db() -> None:
    """Connect to MongoDB and ensure indexes. Call once at app startup."""
    global _client, _db
    try:
        uri = os.environ.get("MONGODB_URI", "mongodb://root:password@localhost:27017/?authSource=admin&directConnection=true")
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
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
        return doc.get("x_mitre_version")
    except PyMongoError as e:
        raise MitreDBError(f"Failed to get MITRE version: {e}") from e


async def list_mitre_versions() -> list[dict]:
    """
    Return all available MITRE versions from mitre_documents.
    Each item has x_mitre_version (_id) and metadata (MitreMetadata fields).
    """
    try:
        collection = _get_db()[COLLECTION_DOCUMENTS]
        cursor = collection.find(
            {},
            {"_id": 1, "metadata": 1},
        ).sort("metadata.last_modified", -1)
        docs = await cursor.to_list(length=None)
        return [
            {
                "x_mitre_version": doc["_id"],
                "metadata": doc.get("metadata", {}),
            }
            for doc in docs
        ]
    except PyMongoError as e:
        raise MitreDBError(f"Failed to list MITRE versions: {e}") from e


async def _entity_docs_with_embeddings(content: MitreBundle) -> list[dict]:
    """
    Build entity documents with embedding field for name+description.
    Uses LM Studio (nomic-embed) via OpenAI-compatible embeddings API.
    """
    entity_docs = []
    docs_with_text = []
    for obj in content.objects:
        doc = {"_id": obj.id, **obj.model_dump(mode="json")}
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
VECTOR_SEARCH_INDEX_NAME = os.environ.get("VECTOR_SEARCH_INDEX_NAME", "mitre_entities_vector")
VECTOR_EMBEDDING_DIMENSIONS = 768


async def _ensure_vector_search_index() -> None:
    """
    Create the vector search index on mitre_entities if missing.
    Only succeeds on MongoDB Atlas (createSearchIndexes is Atlas-only).
    On local MongoDB we log and continue; search_entities_by_embedding will use the in-app fallback.
    """
    try:
        res = await _get_db().command(
            {
                "createSearchIndexes": COLLECTION_LATEST_ENTITIES,
                "indexes": [
                    {
                        "name": VECTOR_SEARCH_INDEX_NAME,
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
            logger.info(
                "Vector search index created: %s",
                [x.get("name") for x in res["indexesCreated"]],
            )
        elif res.get("ok") == 1:
            # Index may already exist (no indexesCreated)
            logger.debug("Vector search index already exists or creation skipped")
    except PyMongoError as e:
        logger.warning(
            "Could not create vector search index (use Atlas or rely on in-app fallback): %s",
            e,
        )


async def search_entities_by_embedding(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    """
    Return top_k MITRE entities most similar to query_embedding using MongoDB Atlas $vectorSearch.
    Requires a vector search index on the collection (path: embedding, cosine similarity).
    Each returned dict has entity fields (type, name, description, etc.), no embedding, plus _score.
    """
    if not query_embedding or top_k <= 0:
        return []
    num_candidates = max(100, top_k * 20)  # Atlas recommendation for ANN recall
    # Fetch extra so that after excluding relationships we still have top_k (filter can't use unindexed 'type')
    search_limit = max(top_k * 10, 50)
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_SEARCH_INDEX_NAME,
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
            f"Vector search failed (is Atlas vector index '{VECTOR_SEARCH_INDEX_NAME}' defined?): {e}"
        ) from e
    return list(docs)


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
        # 4. Sync to Neo4j (best-effort; log and continue on failure)
        try:
            await store_mitre_bundle(content)
        except Exception as e:
            logger.warning("Neo4j sync failed after put_mitre_document: %s", e)
    except PyMongoError as e:
        raise MitreDBError(f"Failed to store MITRE document: {e}") from e


async def insert_mitre_document(
    x_mitre_version: str,
    content: MitreBundle,
    metadata: MitreMetadata,
) -> None:
    """
    Create a new MITRE document (POST-like). Fails with DuplicateVersionError
    if a document for this x_mitre_version already exists.
    """
    db = _get_db()
    docs_collection = db[COLLECTION_DOCUMENTS]
    entities_collection = db[COLLECTION_LATEST_ENTITIES]
    schema_collection = db[COLLECTION_CURRENT_SCHEMA]

    try:
        # 1. Insert new MITRE document by version (no replace)
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
        # 4. Sync to Neo4j (best-effort; log and continue on failure)
        try:
            await store_mitre_bundle(content)
        except Exception as e:
            logger.warning("Neo4j sync failed after insert_mitre_document: %s", e)
    except PyMongoError as e:
        raise MitreDBError(f"Failed to store MITRE document: {e}") from e
