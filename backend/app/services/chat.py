"""Chat completion via LM Studio with RAG (MITRE entities)."""
from __future__ import annotations

import logging

from app.config import settings
from app.services.messages import get_last_user_content, to_langchain_messages
from app.services.protocols import LLMService, RetrievalService

logger = logging.getLogger(__name__)

# System message: RAG instruction. "Relevant entities" block is appended when context is retrieved.
SYSTEM_MESSAGE = (
    "You answer questions about MITRE ATT&CK using the relevant entities provided below.\n"
    "- Base your answers on the 'Relevant entities' section when present. Cite specific techniques, tactics, or other entities where helpful.\n"
    "- If the context does not contain relevant information for the question, say so clearly and do not invent details.\n"
    "- Be concise and accurate. If unsure, indicate uncertainty rather than guessing."
)


class RagChatService:
    def __init__(
        self,
        retrieval: RetrievalService,
        llm: LLMService,
        *,
        rag_top_k: int | None = None,
    ) -> None:
        self._retrieval = retrieval
        self._llm = llm
        self._rag_top_k = rag_top_k if rag_top_k is not None else settings.rag_top_k

    async def chat(self, messages: list[dict[str, str]]) -> tuple[str, str]:
        last_user = get_last_user_content(messages)
        try:
            rag_context = await self._retrieval.get_context(
                last_user, top_k=self._rag_top_k
            )
        except Exception as e:
            logger.warning("RAG failed, continuing without context: %s", e)
            rag_context = ""
        if not rag_context.strip():
            logger.info("Chat using no RAG context (query=%r)", last_user[:80] if last_user else "")
        system_content = SYSTEM_MESSAGE
        if rag_context.strip():
            system_content += "\n\nRelevant entities:\n" + rag_context.strip()
        lc_messages = to_langchain_messages(messages, system_content)
        return await self._llm.invoke(lc_messages)
