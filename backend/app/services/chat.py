"""Chat completion service via LM Studio with LangChain and RAG (MongoDB embedded entities)."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.services.rag import get_relevant_mitre_context
import logging

logger = logging.getLogger(__name__)

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
            rag_context = await get_relevant_mitre_context(last_user_content, top_k=settings.rag_top_k)
        except Exception as e:
            logger.error("Chat: RAG context retrieval failed, continuing without context:", e)

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

    reply = (response.content or "").strip() if hasattr(response, "content") else ""
    model_used = getattr(response, "response_metadata", {}).get("model_name") or settings.chat_model
    return reply, model_used
