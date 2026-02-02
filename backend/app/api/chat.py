"""Chatbot API routes — LM Studio (google/gemma-3-4b)."""
from fastapi import APIRouter, HTTPException

from app.db.mongo import MitreDBError
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import chat

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest) -> ChatResponse:
    """
    Multi-turn chat with the chatbot (LM Studio, google/gemma-3-4b).
    Send `messages` (conversation history; last message should be from the user) and optional `system` prompt.
    Ensure LM Studio is running with the model loaded at LM_STUDIO_URI (default http://localhost:1234/v1).
    """
    try:
        messages_dicts = [{"role": m.role, "content": m.content} for m in body.messages]
        reply, model = await chat(messages_dicts, body.system)
        return ChatResponse(reply=reply, model=model)
    except MitreDBError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database or vector search unavailable: {e!s}",
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e) or "LLM service unavailable (is LM Studio running?).",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Chat service unavailable: {e!s}",
        ) from e
