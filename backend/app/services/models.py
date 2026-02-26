"""Strict dataclass models for services (no dicts)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ChatMessage:
    """A single message in a conversation."""

    role: Literal["user", "assistant", "system"]
    content: str
