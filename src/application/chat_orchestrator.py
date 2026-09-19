"""Application-level conversation orchestration.

The application layer owns the use-case boundary while transport and legacy
implementations stay behind an injected port.  The default factory is resolved
through the composition root, so importing a use case does not import FastAPI
or the legacy service graph.
"""

from collections.abc import Callable, Iterable
from typing import Any

from src.ports.chat import ChatPort


def _default_backend() -> ChatPort:
    """Resolve the compatibility backend from the composition root lazily."""
    from src.bootstrap.composition import create_chat_backend

    return create_chat_backend()


class ChatOrchestrator:
    """Stable application use case for synchronous and streaming chat."""

    def __init__(self, backend_factory: Callable[[], ChatPort] | None = None) -> None:
        self._backend_factory = backend_factory or _default_backend
        # The default composition is deliberately resolved per turn so hot
        # configuration changes and compatibility adapters remain observable.
        # Explicitly injected backends stay cached for normal application use.
        self._cache_backend = backend_factory is not None
        self._backend: ChatPort | None = None

    def _get_backend(self) -> ChatPort:
        if not self._cache_backend:
            return self._backend_factory()
        if self._backend is None:
            self._backend = self._backend_factory()
        return self._backend

    def answer(self, query: str, session_id: str | None = None):
        return self._get_backend().answer(query, session_id)

    def stream(self, query: str, session_id: str | None, stop_event: Any) -> Iterable[dict]:
        return self._get_backend().stream(query, session_id, stop_event)

    def resume(
        self,
        session_id: str,
        decision: str,
        message: str | None,
        stop_event: Any,
        decisions: list[str] | None = None,
    ) -> Iterable[dict]:
        return self._get_backend().resume(
            session_id,
            decision,
            message,
            stop_event,
            decisions=decisions,
        )


default_orchestrator = ChatOrchestrator()
