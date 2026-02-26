"""Message conversion for chat (LangChain)."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.models import ChatMessage


def get_last_user_content(messages: list[ChatMessage]) -> str:
    """Content of the last user message, or empty string."""
    for m in reversed(messages):
        if m.role == "user":
            return (m.content or "").strip()
    return ""


def to_langchain_message(m: ChatMessage) -> HumanMessage | AIMessage | SystemMessage:
    role = m.role.strip().lower() if m.role else "user"
    content = (m.content or "").strip()
    if role == "system":
        return SystemMessage(content=content or " ")
    if role == "assistant":
        return AIMessage(content=content or " ")
    return HumanMessage(content=content)


def to_langchain_messages(
    messages: list[ChatMessage],
    system_content: str,
) -> list[HumanMessage | AIMessage | SystemMessage]:
    """System message first, then conversation messages."""
    result: list[HumanMessage | AIMessage | SystemMessage] = [
        SystemMessage(content=system_content.strip())
    ]
    for m in messages:
        result.append(to_langchain_message(m))
    return result
