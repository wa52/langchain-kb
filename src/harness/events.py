"""Framework-free event primitives shared by channels and plugins."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventBus:
    """In-process event fan-out with failure isolation between subscribers."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event: Event) -> None:
        handlers = [*self._subscribers.get(event.type, []), *self._subscribers.get("*", [])]
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # Observability plugins must not break an Agent turn.
                continue
