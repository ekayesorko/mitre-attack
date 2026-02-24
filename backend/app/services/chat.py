"""Chat completion service via LM Studio with LangChain and RAG (MongoDB embedded entities)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.services.rag import get_relevant_mitre_context

logger = logging.getLogger(__name__)

# Hardcoded system prompt for the chatbot (not taken from user).
CHAT_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions about MITRE ATT&CK. "
    "Use the provided context about MITRE entities when relevant. "
    "If the context does not contain relevant information, say so."
)

ChatRole = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class ChatMessage:
    """A single message in a conversation (service layer)."""
    role: ChatRole
    content: str


@dataclass(frozen=True)
class ChatResult:
    """Result of a chat completion."""
    reply: str
    model: str


def _to_langchain_message(m: ChatMessage) -> HumanMessage | AIMessage | SystemMessage:
    role = m.role.strip().lower() if m.role else "user"
    content = (m.content or "").strip()
    if role == "system":
        return SystemMessage(content=content or " ")
    if role == "assistant":
        return AIMessage(content=content or " ")
    return HumanMessage(content=content or "Hello.")


async def chat(messages: list[ChatMessage]) -> ChatResult:
    """
    Multi-turn chat with RAG: retrieves relevant MITRE entities from MongoDB (pre-embedded),
    injects them as context, then uses LangChain ChatOpenAI (LM Studio) to generate a reply.
    """
    # Last user message drives RAG retrieval
    last_user_content = ""
    for m in reversed(messages):
        if (m.role or "").strip().lower() == "user":
            last_user_content = (m.content or "").strip()
            break

    rag_context = ""
    if last_user_content:
        try:
            rag_context = await get_relevant_mitre_context(last_user_content, top_k=settings.rag_top_k)
        except Exception as e:
            logger.error("Chat: RAG context retrieval failed, continuing without context:", e)

    # Build system block: hardcoded prompt + RAG context
    system_parts: list[str] = [CHAT_SYSTEM_PROMPT]
    if rag_context:
        system_parts.append(
            "Use the following relevant MITRE ATT&CK entities to answer the user. "
            "If the context does not contain relevant information, say so.\n\n"
            f"Relevant entities:\n{rag_context}"
        )
    system_content = "\n\n".join(system_parts)

    llm = ChatOpenAI(
        model=settings.chat_model,
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        temperature=0.7,
        max_tokens=1024,
    )

    lc_messages: list[HumanMessage | AIMessage | SystemMessage] = []
    if system_content:
        lc_messages.append(SystemMessage(content=system_content))
    for m in messages:
        lc_messages.append(_to_langchain_message(m))
    if not any(isinstance(msg, HumanMessage) for msg in lc_messages):
        lc_messages.append(HumanMessage(content="Hello."))

    try:
        response = await llm.ainvoke(lc_messages)
    except Exception as e:
        logger.error("Chat: LLM invocation failed")
        raise RuntimeError(f"LLM unavailable (is LM Studio running?): {e}") from e

    reply: str = (response.content or "").strip() if hasattr(response, "content") else ""
    model_used: str = (
        getattr(response, "response_metadata", {}).get("model_name") or settings.chat_model
    )
    return ChatResult(reply=reply, model=model_used)
