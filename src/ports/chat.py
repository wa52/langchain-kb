"""Application-facing conversation port."""

from collections.abc import Iterable
from typing import Any, Protocol


class ChatPort(Protocol):
    def answer(self, query: str, session_id: str | None = None) -> tuple[str, str, float]: ...

    def stream(self, query: str, session_id: str | None, stop_event: Any) -> Iterable[dict]: ...

    def resume(self, session_id: str, decision: str, message: str | None, stop_event: Any, decisions: list[str] | None = None) -> Iterable[dict]: ...
