"""Chatbot API routes — LM Studio (google/gemma-3-4b)."""
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_chat_service
from app.db.mongo import MitreDBError
from app.exceptions import LLMUnavailableError, ServiceError
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.protocols import ChatService

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat_endpoint(
    body: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """
    Multi-turn chat with the chatbot (LM Studio, google/gemma-3-4b).
    Send `messages` (conversation history; last message should be from the user).
    System prompt is fixed; ensure LM Studio is running at LM_STUDIO_URI (default http://localhost:1234/v1).
    """
    try:
        messages_dicts = [{"role": m.role, "content": m.content} for m in body.messages]
        reply, model = await chat_service.chat(messages_dicts)
        return ChatResponse(reply=reply, model=model)
    except MitreDBError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database or vector search unavailable: {e!s}",
        ) from e
    except LLMUnavailableError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e) or "LLM service unavailable (is LM Studio running?).",
        ) from e
    except ServiceError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Chat service unavailable: {e!s}",
        ) from e
