"""Chat completion service via LM Studio with LangChain and RAG (MongoDB embedded entities)."""
from __future__ import annotations

import logging
import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.services.rag import get_relevant_mitre_context

logger = logging.getLogger(__name__)

LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_URI", "http://localhost:1234/v1").rstrip("/")
if not LM_STUDIO_BASE_URL.endswith("/v1"):
    LM_STUDIO_BASE_URL = LM_STUDIO_BASE_URL.rstrip("/") + "/v1"
CHAT_MODEL = os.environ.get("CHAT_MODEL", "google/gemma-3-4b")
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "5"))


def _to_langchain_message(m: dict) -> HumanMessage | AIMessage | SystemMessage:
    role = (m.get("role") or "user").strip().lower()
    content = (m.get("content") or "").strip()
    if role == "system":
        return SystemMessage(content=content or " ")
    if role == "assistant":
        return AIMessage(content=content or " ")
    return HumanMessage(content=content or "Hello.")


async def chat(
    messages: list[dict[str, str]],
    system: str | None = None,
) -> tuple[str, str]:
    """
    Multi-turn chat with RAG: retrieves relevant MITRE entities from MongoDB (pre-embedded),
    injects them as context, then uses LangChain ChatOpenAI (LM Studio) to generate a reply.
    messages: list of {"role": "user"|"assistant"|"system", "content": "..."}.
    """
    # Last user message drives RAG retrieval
    last_user_content = ""
    for m in reversed(messages):
        if (m.get("role") or "").strip().lower() == "user":
            last_user_content = (m.get("content") or "").strip()
            break

    rag_context = ""
    if last_user_content:
        try:
            rag_context = await get_relevant_mitre_context(last_user_content, top_k=RAG_TOP_K)
        except Exception as e:
            logger.warning("Chat: RAG context retrieval failed, continuing without context: %s", e)

    # Build system block: optional user system + RAG context
    system_parts = []
    if system and system.strip():
        system_parts.append(system.strip())
    if rag_context:
        system_parts.append(
            "Use the following relevant MITRE ATT&CK entities to answer the user. "
            "If the context does not contain relevant information, say so.\n\n"
            f"Relevant entities:\n{rag_context}"
        )
    system_content = "\n\n".join(system_parts) if system_parts else None

    llm = ChatOpenAI(
        model=CHAT_MODEL,
        base_url=LM_STUDIO_BASE_URL,
        api_key=os.environ.get("LM_STUDIO_API_KEY", "lm-studio"),
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
        logger.exception("Chat: LLM invocation failed")
        raise RuntimeError(f"LLM unavailable (is LM Studio running?): {e}") from e

    reply = (response.content or "").strip() if hasattr(response, "content") else ""
    model_used = getattr(response, "response_metadata", {}).get("model_name") or CHAT_MODEL
    return reply, model_used
