"""Optional Agent Runtime seam."""

from collections.abc import Iterable
from typing import Any, Callable, Protocol


class AgentRuntime(Protocol):
    def run(self, query: str, session_id: str | None = None) -> str: ...

    def stream(self, query: str, session_id: str | None = None) -> Iterable[str]: ...

    def stream_messages(
        self,
        messages: list[dict[str, Any]],
        session_id: str,
        *,
        on_tool: Callable[[str], None] | None = None,
        on_interrupt: Callable[[Any], None] | None = None,
        on_tool_result: Callable[[dict], None] | None = None,
        on_trace_run: Callable[[str], None] | None = None,
        stream_input: Any = None,
    ) -> Iterable[str]: ...

    def cancel(self, session_id: str) -> None: ...
