"""FastAPI dependency injection: read service instances from app.state (set in lifespan)."""
from __future__ import annotations

from fastapi import Request

from app.services.protocols import (
    ChatService,
    EmbeddingService,
    LLMService,
    RetrievalService,
)


def get_embedding_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service


def get_llm_service(request: Request) -> LLMService:
    return request.app.state.llm_service


def get_retrieval_service(request: Request) -> RetrievalService:
    return request.app.state.retrieval_service


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service
