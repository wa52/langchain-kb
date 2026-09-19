"""Conversation use case facade independent of FastAPI and LangGraph."""

from collections.abc import Iterable
from typing import Any

from src.application.chat_orchestrator import default_orchestrator
from src.application.citations import extract_sources


def chat_with_rag(query: str, session_id: str | None = None):
    return default_orchestrator.answer(query, session_id)


def stream_chat_events(query: str, session_id: str | None, stop_event: Any) -> Iterable[dict]:
    return default_orchestrator.stream(query, session_id, stop_event)


def resume_chat_events(session_id: str, decision: str, message: str | None, stop_event: Any, decisions: list[str] | None = None) -> Iterable[dict]:
    return default_orchestrator.resume(session_id, decision, message, stop_event, decisions=decisions)
