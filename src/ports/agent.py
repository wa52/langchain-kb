"""Optional Agent Runtime seam."""

from collections.abc import Iterable
from typing import Protocol


class AgentRuntime(Protocol):
    def run(self, query: str, session_id: str | None = None) -> str: ...

    def stream(self, query: str, session_id: str | None = None) -> Iterable[str]: ...

    def cancel(self, session_id: str) -> None: ...
