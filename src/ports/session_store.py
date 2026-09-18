"""Persistence port for conversation sessions."""

from typing import Protocol


class SessionStore(Protocol):
    def list(self) -> list[dict]: ...

    def load(self, session_id: str) -> list[dict] | None: ...

    def delete(self, session_id: str) -> bool: ...
