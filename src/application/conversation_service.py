"""Deep application module for direct and Agent-backed conversations."""

import time
from uuid import uuid4
from collections.abc import Callable, Iterator
from typing import Any

from src.harness import AgentRunTrace


class ConversationService:
    """Own the conversation use case behind three transport-neutral methods."""

    def __init__(
        self,
        *,
        store_factory: Callable[[], Any],
        route_query: Callable[[str, list[dict]], Any],
        direct_route: Any,
        agent_route: Any,
        direct_answer: Callable[[list[dict]], str],
        stream_direct_answer: Callable[[list[dict]], Iterator[str]],
        trim_direct_history: Callable[[list[dict]], list[dict]],
        model_messages: Callable[[list[dict]], list[dict]],
        compress_history: Callable[[list[dict]], list[dict]],
        agent_runtime_factory: Callable[[], Any],
        serialize_messages: Callable[[list], list[dict]],
        build_sources: Callable[[str], list[dict]],
        verify_agent_run: Callable[[str, list[dict], bool], dict],
        resume_command: Callable[[list[str], str | None], Any],
    ) -> None:
        self._store_factory = store_factory
        self._route_query = route_query
        self._direct_route = direct_route
        self._agent_route = agent_route
        self._direct_answer = direct_answer
        self._stream_direct_answer = stream_direct_answer
        self._trim_direct_history = trim_direct_history
        self._model_messages = model_messages
        self._compress_history = compress_history
        self._agent_runtime_factory = agent_runtime_factory
        self._serialize_messages = serialize_messages
        self._build_sources = build_sources
        self._verify_agent_run = verify_agent_run
        self._resume_command = resume_command

    def _messages(self, query: str, session_id: str | None, store: Any) -> list[dict]:
        messages: list[dict] = []
        if session_id:
            for message in store.load(session_id) or []:
                if isinstance(message, dict):
                    normalized = {"role": message.get("role", ""), "content": message.get("content", "")}
                    for key in ("route", "tools"):
                        if key in message:
                            normalized[key] = message[key]
                    messages.append(normalized)
                else:
                    messages.append({
                        "role": getattr(message, "type", getattr(message, "role", "")),
                        "content": getattr(message, "content", ""),
                    })
        messages.append({"role": "user", "content": query})
        return messages

    def answer(self, query: str, session_id: str | None = None) -> tuple[str, str, float]:
        started = time.time()
        store = self._store_factory()
        session_id = session_id or store.allocate()
        with store.lock(session_id):
            messages = self._messages(query, session_id, store)
            route = self._route_query(query, messages[:-1])
            if route == self._direct_route:
                answer = self._direct_answer(self._trim_direct_history(messages))
                history = self._serialize_messages(messages) + [
                    {"role": "assistant", "content": answer, "route": self._direct_route}
                ]
                return answer, store.save(history, session_id), round((time.time() - started) * 1000, 2)

            agent_messages = self._model_messages(self._compress_history(messages))
            trace = AgentRunTrace(run_id=uuid4().hex, query=query)
            answer = "".join(self._agent_runtime_factory().stream_messages(agent_messages, session_id, trace=trace))
            history = self._serialize_messages(messages) + [
                {"role": "assistant", "content": answer, "route": self._agent_route, "trace": trace.snapshot()}
            ]
            new_session_id = store.save(history, session_id)
        return answer, new_session_id, round((time.time() - started) * 1000, 2)

    def stream(self, query: str, session_id: str | None, stop_event: Any) -> Iterator[dict]:
        store = self._store_factory()
        session_id = session_id or store.allocate()
        with store.lock(session_id):
            yield {"type": "message_start", "data": {"session_id": session_id}}
            started = time.time()
            messages = self._messages(query, session_id, store)
            route = self._route_query(query, messages[:-1])
            if route == self._direct_route:
                yield from self._stream_direct(messages, session_id, stop_event, store, started)
                return
            yield from self._stream_agent(messages, session_id, stop_event, store, started)

    def _stream_direct(self, messages, session_id, stop_event, store, started) -> Iterator[dict]:
        parts: list[str] = []
        failed = False
        try:
            for chunk in self._stream_direct_answer(self._trim_direct_history(messages)):
                if stop_event.is_set():
                    break
                parts.append(chunk)
                yield {"type": "token", "data": {"text": chunk}}
        except Exception:
            failed = True
            raise
        finally:
            answer = "".join(parts)
            interrupted = stop_event.is_set() or failed
            history = self._serialize_messages(messages) + [{
                "role": "assistant", "content": answer, "interrupted": interrupted, "route": self._direct_route,
            }]
            new_session_id = store.save(history, session_id)
        yield {"type": "sources", "data": {"sources": []}}
        yield {"type": "message_end", "data": {
            "session_id": new_session_id, "elapsed_ms": round((time.time() - started) * 1000, 2),
            "interrupted": interrupted, "waiting_approval": False, "route": self._direct_route,
        }}

    def _stream_agent(self, messages, session_id, stop_event, store, started) -> Iterator[dict]:
        tools: list[str] = []
        interrupts: list[Any] = []
        results: list[dict] = []
        trace = AgentRunTrace(run_id=uuid4().hex, query=messages[-1].get("content", ""))
        parts: list[str] = []
        failed = False

        def on_tool(name: str) -> None:
            if name not in tools:
                tools.append(name)

        def on_interrupt(value: Any) -> None:
            interrupts.extend(value if isinstance(value, (list, tuple)) else [value])

        try:
            for chunk in self._agent_runtime_factory().stream_messages(
                self._model_messages(self._compress_history(messages)), session_id,
                on_tool=on_tool, on_interrupt=on_interrupt, on_tool_result=results.append, trace=trace,
            ):
                if stop_event.is_set():
                    break
                if chunk:
                    parts.append(chunk)
                    yield {"type": "token", "data": {"text": chunk}}
        except Exception:
            failed = True
            raise
        finally:
            answer = "".join(parts)
            interrupted = stop_event.is_set() or failed
            assistant = {"role": "assistant", "content": answer, "interrupted": interrupted, "route": self._agent_route}
            if tools:
                assistant["tools"] = list(tools)
            if interrupts:
                assistant["pending_approval"] = True
            if results or interrupts:
                assistant["verification"] = self._verify_agent_run(answer, results, bool(interrupts))
            assistant["trace"] = trace.snapshot()
            new_session_id = store.save(self._serialize_messages(messages) + [assistant], session_id)
        if interrupts:
            yield {"type": "approval_required", "data": {"session_id": session_id, "interrupts": [str(x) for x in interrupts]}}
        if tools:
            yield {"type": "tool", "data": {"tools": tools}}
        if results or interrupts:
            yield {"type": "verification", "data": self._verify_agent_run(answer, results, bool(interrupts))}
        yield {"type": "sources", "data": {"sources": self._build_sources(answer)}}
        yield {"type": "message_end", "data": {
            "session_id": new_session_id, "elapsed_ms": round((time.time() - started) * 1000, 2),
            "interrupted": interrupted, "waiting_approval": bool(interrupts), "route": self._agent_route,
        }}

    def resume(self, session_id: str, decision: str, message: str | None, stop_event: Any, decisions: list[str] | None = None) -> Iterator[dict]:
        store = self._store_factory()
        with store.lock(session_id):
            tools: list[str] = []
            interrupts: list[Any] = []
            results: list[dict] = []

            def on_tool(name: str) -> None:
                if name not in tools:
                    tools.append(name)

            def on_interrupt(value: Any) -> None:
                interrupts.extend(value if isinstance(value, (list, tuple)) else [value])

            parts = []
            trace = AgentRunTrace(run_id=uuid4().hex, query=message or "")
            command = self._resume_command(decisions or [decision], message)
            for chunk in self._agent_runtime_factory().stream_messages(
                [], session_id, on_tool=on_tool, on_interrupt=on_interrupt,
                on_tool_result=results.append, stream_input=command, trace=trace,
            ):
                if stop_event.is_set():
                    break
                if chunk:
                    parts.append(chunk)
            answer = "".join(parts)
            history = store.load(session_id) or []
            if history and history[-1].get("pending_approval"):
                history.pop()
            assistant = {"role": "assistant", "content": answer, "interrupted": bool(stop_event.is_set())}
            if tools:
                assistant["tools"] = tools
            if interrupts:
                assistant["pending_approval"] = True
            if results or interrupts:
                assistant["verification"] = self._verify_agent_run(answer, results, bool(interrupts))
            assistant["trace"] = trace.snapshot()
            store.save(history + [assistant], session_id)
            yield {"type": "token", "data": {"text": answer}}
            if interrupts:
                yield {"type": "approval_required", "data": {"session_id": session_id, "interrupts": [str(x) for x in interrupts]}}
            if results or interrupts:
                yield {"type": "verification", "data": self._verify_agent_run(answer, results, bool(interrupts))}
            yield {"type": "message_end", "data": {
                "session_id": session_id, "interrupted": bool(stop_event.is_set()), "waiting_approval": bool(interrupts),
            }}
