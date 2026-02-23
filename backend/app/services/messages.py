"""Message conversion for chat (LangChain)."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def get_last_user_content(messages: list[dict[str, str]]) -> str:
    """Content of the last user message, or empty string."""
    for m in reversed(messages):
        if (m.get("role") or "").strip().lower() == "user":
            return (m.get("content") or "").strip()
    return ""


def to_langchain_message(m: dict) -> HumanMessage | AIMessage | SystemMessage:
    role = (m.get("role") or "user").strip().lower()
    content = (m.get("content") or "").strip()
    if role == "system":
        return SystemMessage(content=content or " ")
    if role == "assistant":
        return AIMessage(content=content or " ")
    return HumanMessage(content=content)


def to_langchain_messages(
    messages: list[dict[str, str]],
    system_content: str,
) -> list[HumanMessage | AIMessage | SystemMessage]:
    """System message first, then conversation messages."""
    result: list[HumanMessage | AIMessage | SystemMessage] = [
        SystemMessage(content=system_content.strip())
    ]
    for m in messages:
        result.append(to_langchain_message(m))
    return result
