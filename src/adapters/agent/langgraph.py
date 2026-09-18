"""LangGraph adapter for the project-owned AgentRuntime port."""

from collections.abc import Callable, Iterable
from typing import Any


class LangGraphAgentRuntime:
    """Translate the current LangGraph agent into a framework-neutral seam.

    The adapter accepts its factory and stream function so tests and a future
    Agent Runtime can replace LangGraph without changing application code.
    """

    def __init__(
        self,
        agent_factory: Callable[[], Any] | None = None,
        stream_fn: Callable[..., Iterable[str]] | None = None,
    ) -> None:
        self._agent_factory = agent_factory
        self._stream_fn = stream_fn
        self._agent: Any = None
        self._cancelled: set[str] = set()

    def _get_agent(self) -> Any:
        if self._agent is None:
            factory = self._agent_factory
            if factory is None:
                from src.agent.rag_agent import create_rag_agent
                factory = create_rag_agent
            self._agent = factory()
        return self._agent

    def _stream(self, agent: Any, messages: list[dict[str, str]]) -> Iterable[str]:
        stream_fn = self._stream_fn
        if stream_fn is None:
            from src.agent.rag_agent import stream_rag_response
            stream_fn = stream_rag_response
        return stream_fn(agent, messages)

    def run(self, query: str, session_id: str | None = None) -> str:
        return "".join(self.stream(query, session_id))

    def stream(self, query: str, session_id: str | None = None) -> Iterable[str]:
        if not query.strip():
            raise ValueError("query must not be empty")
        session_id = session_id or "default"
        self._cancelled.discard(session_id)
        agent = self._get_agent()
        messages = [{"role": "user", "content": query}]
        try:
            configured = agent.with_config({"configurable": {"thread_id": session_id}})
        except (AttributeError, TypeError):
            configured = agent
        for chunk in self._stream(configured, messages):
            if session_id in self._cancelled:
                break
            if chunk:
                yield str(chunk)

    def cancel(self, session_id: str) -> None:
        self._cancelled.add(session_id)
