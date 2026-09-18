"""Append-only session log primitive for durable adapters."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class SessionEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionLog:
    """Small stable interface; file/DB/event-store persistence is an adapter."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._events: list[SessionEvent] = []

    def append(self, event_type: str, **payload: Any) -> SessionEvent:
        event = SessionEvent(event_type, payload)
        self._events.append(event)
        return event

    def snapshot(self) -> tuple[SessionEvent, ...]:
        return tuple(self._events)
