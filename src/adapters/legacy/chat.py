"""Legacy conversation adapter.

This is intentionally the only compatibility module that knows the old API
service implementation. It can be replaced by a native Application adapter
without changing transports.
"""

from typing import Any


class LegacyChatAdapter:
    def _module(self):
        from src.api.services import chat
        return chat

    def answer(self, query: str, session_id: str | None = None):
        return self._module().chat_with_rag(query, session_id)

    def stream(self, query: str, session_id: str | None, stop_event: Any):
        return self._module().stream_chat_events(query, session_id, stop_event)

    def resume(self, session_id: str, decision: str, message: str | None, stop_event: Any, decisions: list[str] | None = None):
        return self._module().resume_chat_events(session_id, decision, message, stop_event, decisions=decisions)
