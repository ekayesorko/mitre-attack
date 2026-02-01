"""Chat API request/response schemas for LM Studio chatbot."""
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single message in a conversation."""

    role: Literal["user", "assistant", "system"] = Field(
        ..., description="Who sent this message (user, assistant, or system)"
    )
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Multi-turn chat request: full conversation plus optional system prompt."""

    messages: list[ChatMessage] = Field(
        ...,
        min_length=1,
        description="Conversation history. Last message should be from the user.",
    )
    system: str | None = Field(
        None,
        description="Optional system prompt (prepended before messages).",
    )


class ChatResponse(BaseModel):
    """Chat completion response from LM Studio (google/gemma-3-4b)."""

    reply: str = Field(..., description="Assistant reply text")
    model: str = Field(..., description="Model used (e.g. google/gemma-3-4b)")
