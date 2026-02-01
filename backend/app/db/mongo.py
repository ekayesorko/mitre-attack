"""MongoDB access for MITRE documents. Three collectionections:

- current_schema: single document with current x_mitre_version
- mitre_entities: latest MITRE entities as individual documents (_id = entity id)
- mitre_documents: whole MITRE bundle per version (_id = x_mitre_version)
"""
import os

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.schemas.mitre import MitreBundle, MitreMetadata, MitreObject


class MitreDBError(Exception):
    """Raised when a MongoDB operation fails (connection, timeout, or write error)."""
    pass


class DuplicateVersionError(MitreDBError):
    """Raised when inserting a MITRE document for a version that already exists."""
    pass

CURRENT_DOC_ID = "current"
DATABASE_NAME = "mitre_db"

# collectionection names
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
        uri = os.environ.get("MONGODB_URI", "mongodb://root:password@localhost:27017/?authSource=admin")
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        await _client.admin.command("ping")
        _db = _client[DATABASE_NAME]

        # current_schema: single doc, no index needed beyond _id
        # mitre_entities: index by type for listing/filtering
        await _db[COLLECTION_LATEST_ENTITIES].create_index([("type", 1)])
        # mitre_documents: keyed by version (_id), no extra index needed
        await _db[COLLECTION_DOCUMENTS].create_index([("_id", 1)])
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


async def put_mitre_document(
    x_mitre_version: str,
    content: MitreBundle,
    metadata: MitreMetadata,
) -> None:
    """
    Store MITRE data in three collectionections:
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

        # 2. Replace latest entities: clear and insert current version's entities (each with _id = entity id)
        await entities_collection.delete_many({})
        entity_docs = []
        for obj in content.objects:
            entity_docs.append({
                "_id": obj.id,
                **obj.model_dump(mode="json"),
            })
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
        # 2. Replace latest entities with this version's entities
        await entities_collection.delete_many({})
        entity_docs = [
            {"_id": obj.id, **obj.model_dump(mode="json")}
            for obj in content.objects
        ]
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
