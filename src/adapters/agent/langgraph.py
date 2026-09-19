"""LangGraph adapter for the project-owned AgentRuntime port."""

from collections.abc import Callable, Iterable
import inspect
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

    @staticmethod
    def _bind_session(agent: Any, session_id: str) -> Any:
        try:
            return agent.with_config({"configurable": {"thread_id": session_id}})
        except (AttributeError, TypeError):
            return agent

    @staticmethod
    def _messages_for_session(agent: Any, messages: list[dict[str, Any]], session_id: str) -> list[dict[str, Any]]:
        """Avoid replaying history when a durable Agent thread already exists."""
        try:
            state = agent.get_state({"configurable": {"thread_id": session_id}})
            values = getattr(state, "values", None) or {}
            if values.get("messages"):
                return messages[-1:]
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        return messages

    def _stream(self, agent: Any, messages: list[dict[str, Any]], **kwargs: Any) -> Iterable[str]:
        stream_fn = self._stream_fn
        if stream_fn is None:
            from src.agent.rag_agent import stream_rag_response
            stream_fn = stream_rag_response
        supported = {"on_tool": kwargs["on_tool"]} if kwargs.get("on_tool") is not None else {}
        try:
            parameters = inspect.signature(stream_fn).parameters
            supported.update({
                key: value
                for key, value in kwargs.items()
                if key != "on_tool" and value is not None and key in parameters
            })
        except (TypeError, ValueError):
            pass
        return stream_fn(agent, messages, **supported)

    def run(self, query: str, session_id: str | None = None) -> str:
        return "".join(self.stream(query, session_id))

    def stream(self, query: str, session_id: str | None = None) -> Iterable[str]:
        if not query.strip():
            raise ValueError("query must not be empty")
        session_id = session_id or "default"
        yield from self.stream_messages([{"role": "user", "content": query}], session_id)

    def stream_messages(
        self,
        messages: list[dict[str, Any]],
        session_id: str,
        *,
        on_tool: Callable[[str], None] | None = None,
        on_interrupt: Callable[[Any], None] | None = None,
        on_tool_result: Callable[[dict], None] | None = None,
        stream_input: Any = None,
    ) -> Iterable[str]:
        """Run a prepared chat turn with LangGraph state and tool callbacks."""
        self._cancelled.discard(session_id)
        configured = self._bind_session(self._get_agent(), session_id)
        prepared = self._messages_for_session(configured, messages, session_id)
        for chunk in self._stream(
            configured,
            prepared,
            on_tool=on_tool,
            on_interrupt=on_interrupt,
            on_tool_result=on_tool_result,
            stream_input=stream_input,
        ):
            if session_id in self._cancelled:
                break
            if chunk:
                yield str(chunk)

    def cancel(self, session_id: str) -> None:
        self._cancelled.add(session_id)
