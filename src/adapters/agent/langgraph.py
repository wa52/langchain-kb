"""LangGraph adapter for the project-owned AgentRuntime port."""

from collections.abc import Callable, Iterable
import inspect
from uuid import uuid4
from typing import Any


class LangGraphAgentRuntime:
    """Translate the current LangGraph agent into a framework-neutral seam.

    The adapter accepts its factory and stream function so tests and a future
    Agent Runtime can replace LangGraph without changing application code.
    """

    def __init__(
        self,
        agent_factory: Callable[..., Any] | None = None,
        stream_fn: Callable[..., Iterable[str]] | None = None,
        tool_registry: Any = None,
        tool_selector: Any = None,
    ) -> None:
        self._agent_factory = agent_factory
        self._stream_fn = stream_fn
        self._agent: Any = None
        self._agents: dict[tuple[str, ...] | None, Any] = {}
        self._tool_registry = tool_registry
        self._tool_selector = tool_selector
        self._cancelled: set[str] = set()

    def _get_agent(self, tool_names: tuple[str, ...] | None = None) -> Any:
        if self._tool_selector is None and self._agent is not None:
            return self._agent
        if tool_names not in self._agents:
            factory = self._agent_factory
            if factory is None:
                from src.agent.rag_agent import create_rag_agent
                factory = create_rag_agent
            try:
                signature = inspect.signature(factory)
                supports_selection = "tool_names" in signature.parameters
            except (TypeError, ValueError):
                supports_selection = False
            self._agents[tool_names] = factory(tool_names=tool_names) if supports_selection else factory()
        agent = self._agents[tool_names]
        if self._tool_selector is None:
            self._agent = agent
        return agent

    def _select_tools(self, messages: list[dict[str, Any]]) -> tuple[str, ...] | None:
        if self._tool_selector is None or self._tool_registry is None:
            return None
        query = next(
            (str(message.get("content", "")) for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        return self._tool_selector.select_names(query, self._tool_registry.catalog())

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
        trace: Any = None,
    ) -> Iterable[str]:
        """Run a prepared chat turn with LangGraph state and tool callbacks."""
        self._cancelled.discard(session_id)
        owned_trace = trace is None
        if owned_trace:
            from src.harness import AgentRunTrace
            trace = AgentRunTrace(run_id=uuid4().hex, query=str(messages[-1].get("content", "")) if messages else "")
        if trace is not None:
            trace.emit("agent.run.started", session_id=session_id)
            trace.emit("selector.started")
        selected_tools = self._select_tools(messages)
        if trace is not None:
            trace.selected_tools = tuple(selected_tools or ())
            trace.emit("selector.completed", selected_tools=list(selected_tools or ()))
        configured = self._bind_session(self._get_agent(selected_tools), session_id)
        prepared = self._messages_for_session(configured, messages, session_id)
        try:
            if trace is not None:
                trace.emit("llm.request", messages=len(prepared), selected_tools=list(selected_tools or ()))
            for chunk in self._stream(configured, prepared, on_tool=on_tool, on_interrupt=on_interrupt, on_tool_result=on_tool_result, stream_input=stream_input):
                if session_id in self._cancelled:
                    break
                if chunk:
                    yield str(chunk)
                    if trace is not None:
                        trace.emit("llm.response", final_answer=True)
        finally:
            if trace is not None:
                trace.emit("agent.run.completed", session_id=session_id)
                if owned_trace:
                    from src.harness import trace_store
                    trace_store.put(trace)

    def cancel(self, session_id: str) -> None:
        self._cancelled.add(session_id)
