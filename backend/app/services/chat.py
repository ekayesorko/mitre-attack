"""Chat completion service via LM Studio (OpenAI-compatible API, google/gemma-3-4b)."""
from __future__ import annotations

import os
from openai import AsyncOpenAI

LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_URI", "http://localhost:1234/v1").rstrip("/")
if not LM_STUDIO_BASE_URL.endswith("/v1"):
    LM_STUDIO_BASE_URL = LM_STUDIO_BASE_URL.rstrip("/") + "/v1"
CHAT_MODEL = os.environ.get("CHAT_MODEL", "google/gemma-3-4b")


def _message_to_dict(msg: dict) -> dict[str, str]:
    return {"role": msg["role"], "content": (msg.get("content") or "").strip()}


async def chat(
    messages: list[dict[str, str]],
    system: str | None = None,
) -> tuple[str, str]:
    """
    Send a multi-turn conversation to LM Studio and return (reply_text, model_used).
    messages: list of {"role": "user"|"assistant"|"system", "content": "..."}.
    Uses google/gemma-3-4b by default; set CHAT_MODEL to override.
    """
    client = AsyncOpenAI(
        base_url=LM_STUDIO_BASE_URL,
        api_key=os.environ.get("LM_STUDIO_API_KEY", "lm-studio"),
    )
    payload: list[dict[str, str]] = []
    if system and system.strip():
        payload.append({"role": "system", "content": system.strip()})
    for m in messages:
        payload.append(_message_to_dict(m))
    # Ensure we have at least one user message
    if not any(p["role"] == "user" for p in payload):
        payload.append({"role": "user", "content": "Hello."})

    response = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=payload,
        max_tokens=1024,
        temperature=0.7,
    )
    choice = response.choices[0] if response.choices else None
    reply = (choice.message.content if choice and choice.message else "").strip() or ""
    return reply, response.model or CHAT_MODEL
