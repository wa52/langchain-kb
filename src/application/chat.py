"""Conversation use case facade independent of FastAPI and LangGraph."""

from collections.abc import Iterable
from typing import Any

from src.adapters.legacy.chat import LegacyChatAdapter
from src.ports.chat import ChatPort


_default_chat: ChatPort = LegacyChatAdapter()


def chat_with_rag(query: str, session_id: str | None = None):
    return _default_chat.answer(query, session_id)


def stream_chat_events(query: str, session_id: str | None, stop_event: Any) -> Iterable[dict]:
    return _default_chat.stream(query, session_id, stop_event)


def resume_chat_events(session_id: str, decision: str, message: str | None, stop_event: Any, decisions: list[str] | None = None) -> Iterable[dict]:
    return _default_chat.resume(session_id, decision, message, stop_event, decisions=decisions)


def extract_sources(answer: str) -> list[dict]:
    # Source extraction is a presentation-independent part of the use case;
    # keep the compatibility implementation behind the same seam for now.
    from src.api.services.chat import extract_sources as _extract_sources
    return _extract_sources(answer)
