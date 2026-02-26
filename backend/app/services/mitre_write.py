"""Orchestrator for MITRE write operations: embedding + persistence via MongoDB."""
from __future__ import annotations

import logging

from app.db.mongo import MongoDBRepo
from app.db.neo4j import Neo4jRepo
from app.schemas.db import MitreEntityDoc
from app.schemas.mitre import MitreBundle, MitreMetadata
from app.services.protocols import EmbeddingService
from app.utils.entity_text import entity_text_for_embedding

logger = logging.getLogger(__name__)


async def _build_entity_docs_with_embeddings(
    content: MitreBundle,
    embedding_service: EmbeddingService,
) -> list[MitreEntityDoc]:
    """Build entity documents with embedding field for name+description."""
    entity_docs: list[MitreEntityDoc] = []
    docs_with_text: list[tuple[MitreEntityDoc, str]] = []
    for obj in content.objects:
        doc = MitreEntityDoc(entity=obj, embedding=None)
        entity_docs.append(doc)
        text = entity_text_for_embedding(obj.name, obj.description)
        if text:
            docs_with_text.append((doc, text))
    if docs_with_text:
        texts = [t for _, t in docs_with_text]
        embeddings = await embedding_service.embed_texts_batch(texts)
        for (doc, _), vec in zip(docs_with_text, embeddings):
            # Replace with a new doc that has embedding set (MitreEntityDoc is not frozen)
            idx = entity_docs.index(doc)
            entity_docs[idx] = MitreEntityDoc(entity=doc.entity, embedding=vec)
    return entity_docs


class MitreWriteService:
    """Orchestrates embedding and persistence for MITRE write operations."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        mitre_db: MongoDBRepo,
        neo4j_repo: Neo4jRepo,
    ) -> None:
        self._embedding = embedding_service
        self._mitre_db = mitre_db
        self._neo4j = neo4j_repo

    async def put_document(
        self,
        x_mitre_version: str,
        content: MitreBundle,
        metadata: MitreMetadata,
    ) -> None:
        """Store or replace MITRE document and entities (with embeddings), set current version."""
        entity_docs = await _build_entity_docs_with_embeddings(content, self._embedding)
        await self._mitre_db.put_mitre_document(x_mitre_version, content, metadata, entity_docs)
        try:
            await self._neo4j.store_mitre_bundle(content)
        except Exception as e:
            logger.error("Neo4j sync failed after put_document: %s", e)

    async def insert_document(
        self,
        x_mitre_version: str,
        content: MitreBundle,
        metadata: MitreMetadata,
    ) -> None:
        """Insert new MITRE document and entities (with embeddings); raises if version exists."""
        entity_docs = await _build_entity_docs_with_embeddings(content, self._embedding)
        await self._mitre_db.insert_mitre_document(x_mitre_version, content, metadata, entity_docs)
        try:
            await self._neo4j.store_mitre_bundle(content)
        except Exception as e:
            logger.error("Neo4j sync failed after insert_document: %s", e)
