"""MongoDB access for MITRE documents. Three collections:

- current_schema: single document with current x_mitre_version
- mitre_entities: latest MITRE entities as individual documents (_id = entity id), with optional embedding (name+description)
- mitre_documents: whole MITRE bundle per version (_id = x_mitre_version)

Vector search uses MongoDB Atlas $vectorSearch (requires a vector search index on mitre_entities.embedding).
Set VECTOR_SEARCH_INDEX_NAME to match your Atlas index (default: mitre_entities_vector).
"""
import asyncio
import logging
import time

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.config import settings
from app.schemas.db import EntitySearchResult, MitreEntityDoc, MitreVersionEntry
from app.schemas.mitre import MitreBundle, MitreMetadata, MitreObject

logger = logging.getLogger(__name__)
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


async def _wait_for_vector_index_ready(db: AsyncIOMotorDatabase, timeout_sec: float = 60.0) -> bool:
    """Poll until the vector search index is queryable or timeout. Returns True if ready."""
    collection = db[COLLECTION_LATEST_ENTITIES]
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            cursor = collection.aggregate([
                {"$listSearchIndexes": {"name": settings.vector_search_index_name}}
            ])
            docs = await cursor.to_list(length=1)
            if docs and docs[0].get("queryable") is True:
                logger.info("Vector search index is ready")
                return True
        except PyMongoError as e:
            logger.debug("List search indexes: %s", e)
        await asyncio.sleep(2.0)
    logger.warning("Vector search index not ready within %.0fs", timeout_sec)
    return False


# Atlas vector search index name. Create in Atlas UI (Search → Create Index → JSON editor).
# nomic-embed-text uses 768 dimensions.
VECTOR_EMBEDDING_DIMENSIONS = 768


async def _ensure_vector_search_index(db: AsyncIOMotorDatabase) -> None:
    """
    Create the vector search index on mitre_entities if missing.
    Only succeeds on MongoDB Atlas / Atlas Local (createSearchIndexes is Atlas-only).
    Waits for the index to become queryable so RAG retrieval works on first request.
    """
    try:
        res = await db.command(
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
            logger.info("Vector search index created, waiting for it to be ready")
            await _wait_for_vector_index_ready(db)
        elif res.get("ok") == 1:
            logger.info("Vector search index already exists or creation skipped")
    except PyMongoError as e:
        logger.error("Could not create vector search index: %s", e)


class MongoDBRepo:
    """MongoDB repository for MITRE documents. Injected via app.state (see dependencies.get_mitre_db)."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    async def get_mitre_version(self) -> str | None:
        """Return current x_mitre_version or None if none set."""
        try:
            collection = self._db[COLLECTION_CURRENT_SCHEMA]
            doc = await collection.find_one({"_id": CURRENT_DOC_ID})
            if doc is None:
                return None
            return doc.get("x_mitre_version")
        except PyMongoError as e:
            raise MitreDBError(f"Failed to get MITRE version: {e}") from e

    async def list_mitre_versions(self) -> list[MitreVersionEntry]:
        """
        Return all available MITRE versions from mitre_documents.
        Each item has x_mitre_version (_id) and metadata (MitreMetadata).
        """
        try:
            collection = self._db[COLLECTION_DOCUMENTS]
            cursor = collection.find(
                {},
                {"_id": 1, "metadata": 1},
            ).sort("metadata.last_modified", -1)
            docs = await cursor.to_list(length=None)
            return [
                MitreVersionEntry(
                    x_mitre_version=doc["_id"],
                    metadata=MitreMetadata.model_validate(doc.get("metadata", {})),
                )
                for doc in docs
            ]
        except PyMongoError as e:
            raise MitreDBError(f"Failed to list MITRE versions: {e}") from e

    async def get_mitre_content(self) -> tuple[MitreBundle, MitreMetadata] | None:
        """Return (content, metadata) for current version, or None."""
        try:
            version = await self.get_mitre_version()
            if version is None:
                return None
            collection = self._db[COLLECTION_DOCUMENTS]
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

    async def get_mitre_content_by_version(self, x_mitre_version: str) -> tuple[MitreBundle, MitreMetadata] | None:
        """Return (content, metadata) for the given version, or None if not found."""
        try:
            collection = self._db[COLLECTION_DOCUMENTS]
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

    async def search_entities_by_embedding(
        self,
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
                    "description": 1,
                    "x_mitre_shortname": 1,
                    "_score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        try:
            collection = self._db[COLLECTION_LATEST_ENTITIES]
            cursor = collection.aggregate(pipeline)
            docs = await cursor.to_list(length=top_k)
        except PyMongoError as e:
            raise MitreDBError(
                f"Vector search failed (is Atlas vector index '{settings.vector_search_index_name}' defined?): {e}"
            ) from e
        return [
            EntitySearchResult(
                id=doc.get("id") or doc.get("_id", ""),
                type=doc.get("type"),
                name=doc.get("name"),
                description=doc.get("description"),
                x_mitre_shortname=doc.get("x_mitre_shortname"),
                score=float(doc.get("_score", 0.0)),
            )
            for doc in docs
        ]

    async def search_entities_by_text(self, query: str, top_k: int = 10) -> list[EntitySearchResult]:
        """
        Match query as case-insensitive substring in name only.
        Excludes relationships. Returns same shape as vector search (id, type, name, x_mitre_shortname, score=1.0).
        """
        query = (query or "").strip()
        if not query or top_k <= 0:
            return []
        try:
            collection = self._db[COLLECTION_LATEST_ENTITIES]
            regex = {"$regex": query, "$options": "i"}
            cursor = collection.find(
                {
                    "type": {"$ne": "relationship"},
                    "name": regex,
                },
                {"_id": 1, "id": 1, "type": 1, "name": 1, "description": 1, "x_mitre_shortname": 1},
            ).limit(top_k)
            docs = await cursor.to_list(length=top_k)
            return [
                EntitySearchResult(
                    id=doc.get("id") or doc.get("_id", ""),
                    type=doc.get("type"),
                    name=doc.get("name"),
                    description=doc.get("description"),
                    x_mitre_shortname=doc.get("x_mitre_shortname"),
                    score=1.0,
                )
                for doc in docs
            ]
        except PyMongoError as e:
            raise MitreDBError(f"Text search failed: {e}") from e

    async def _update_mitre_documents(
        self,
        x_mitre_version: str,
        content: MitreBundle,
        metadata: MitreMetadata,
        *,
        upsert: bool = False,
    ) -> None:
        """Update mitre_documents: insert one new version or replace (upsert) existing."""
        collection = self._db[COLLECTION_DOCUMENTS]
        doc = {
            "_id": x_mitre_version,
            "metadata": metadata.model_dump(mode="json"),
            "spec_version": content.spec_version,
            "bundle_id": content.id,
            "objects": [o.model_dump(mode="json") for o in content.objects],
        }
        if upsert:
            await collection.replace_one({"_id": x_mitre_version}, doc, upsert=True)
        else:
            await collection.insert_one(doc)

    async def _update_mitre_entities(self, entity_docs: list[MitreEntityDoc]) -> None:
        """Replace all documents in mitre_entities with the given entity_docs."""
        collection = self._db[COLLECTION_LATEST_ENTITIES]
        await collection.delete_many({})
        if entity_docs:
            await collection.insert_many([ed.to_mongo_doc() for ed in entity_docs])

    async def _update_current_schema(self, x_mitre_version: str) -> None:
        """Set the current x_mitre_version in current_schema."""
        collection = self._db[COLLECTION_CURRENT_SCHEMA]
        await collection.replace_one(
            {"_id": CURRENT_DOC_ID},
            {"_id": CURRENT_DOC_ID, "x_mitre_version": x_mitre_version},
            upsert=True,
        )

    async def put_mitre_document(
        self,
        x_mitre_version: str,
        content: MitreBundle,
        metadata: MitreMetadata,
        entity_docs: list[MitreEntityDoc],
    ) -> None:
        """
        Store MITRE data in three collections:
        - current_schema: set current version
        - mitre_entities: replace with provided entity_docs (pre-built with embeddings by caller)
        - mitre_documents: store whole bundle for this version (_id = version)
        """
        try:
            await self._update_mitre_documents(x_mitre_version, content, metadata, upsert=True)
            await self._update_mitre_entities(entity_docs)
            await self._update_current_schema(x_mitre_version)
        except PyMongoError as e:
            raise MitreDBError(f"Failed to store MITRE document: {e}") from e

    async def insert_mitre_document(
        self,
        x_mitre_version: str,
        content: MitreBundle,
        metadata: MitreMetadata,
        entity_docs: list[MitreEntityDoc],
    ) -> None:
        """Insert new MITRE document and entity_docs (pre-built with embeddings by caller)."""
        try:
            await self._update_mitre_documents(x_mitre_version, content, metadata, upsert=False)
        except DuplicateKeyError as e:
            raise DuplicateVersionError(
                f"MITRE version '{x_mitre_version}' already exists"
            ) from e
        try:
            await self._update_mitre_entities(entity_docs)
            await self._update_current_schema(x_mitre_version)
        except PyMongoError as e:
            raise MitreDBError(f"Failed to store MITRE document: {e}") from e


async def init_mongo_db() -> tuple[AsyncIOMotorClient, MongoDBRepo]:
    """Connect to MongoDB, ensure indexes, and return (client, MongoDB). Store client for close_db at shutdown."""
    client: AsyncIOMotorClient | None = None
    try:
        client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
        await client.admin.command("ping")
        db = client[DATABASE_NAME]

        await db[COLLECTION_LATEST_ENTITIES].create_index([("type", 1)])
        await db[COLLECTION_DOCUMENTS].create_index([("_id", 1)])
        await _ensure_vector_search_index(db)

        return (client, MongoDBRepo(db))
    except PyMongoError as e:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        raise MitreDBError(f"MongoDB connection or init failed: {e}") from e


def close_mongo_db(client: AsyncIOMotorClient) -> None:
    """Close MongoDB connection. Call at app shutdown with client from init_db()."""
    try:
        client.close()
    except Exception:
        raise
