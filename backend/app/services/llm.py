"""LLM invocation via LM Studio (OpenAI-compatible)."""
from __future__ import annotations

import logging

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.exceptions import LLMUnavailableError

logger = logging.getLogger(__name__)

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1024


class LLMService:
    """LM Studio chat LLM implementation."""

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._model = model or settings.chat_model
        self._base_url = base_url or settings.lm_studio_base_url
        self._api_key = api_key or settings.lm_studio_api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        timeout = getattr(settings, "llm_request_timeout", 300.0)
        self.llm = ChatOpenAI(
            model=self._model,
            base_url=self._base_url,
            api_key=self._api_key,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            request_timeout=timeout,
        )

    async def invoke(self, messages: list[BaseMessage]) -> tuple[str, str]:
        try:
            response = await self.llm.ainvoke(messages)
        except Exception as e:
            logger.error("LLM invocation failed: %s", e)
            raise LLMUnavailableError(
                f"LLM unavailable (is LM Studio running?): {e}"
            ) from e
        reply = (
            (response.content or "").strip()
            if hasattr(response, "content")
            else ""
        )
        model_used = (
            getattr(response, "response_metadata", {}).get("model_name")
            or self._model
        )
        return reply, model_used
