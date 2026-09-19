"""Persistence boundary for chat sessions."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any


class ConversationStore:
    """Small port-backed store shared by direct and agent chat engines."""

    def __init__(self, allocate: Callable[[], str], load: Callable[[str], list[dict] | None], save: Callable[[list[dict], str], str], lock: Callable[[str], AbstractContextManager[Any]]) -> None:
        self._allocate, self._load, self._save, self._lock = allocate, load, save, lock

    def allocate(self) -> str:
        return self._allocate()

    def load(self, session_id: str) -> list[dict] | None:
        return self._load(session_id)

    def save(self, messages: list[dict], session_id: str) -> str:
        return self._save(messages, session_id)

    def lock(self, session_id: str) -> AbstractContextManager[Any]:
        return self._lock(session_id)
