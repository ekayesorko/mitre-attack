"""Chat API request/response schemas for LM Studio chatbot."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ChatMessage:
    """A single message in a conversation (dataclass for internal use)."""

    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    """Multi-turn chat request: full conversation history."""

    messages: list[ChatMessage] = Field(
        ...,
        min_length=1,
        description="Conversation history. Last message should be from the user.",
    )


class ChatResponse(BaseModel):
    """Chat completion response."""

    reply: str = Field(..., description="Assistant reply text")
