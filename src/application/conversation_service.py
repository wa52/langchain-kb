"""Deep application module for direct and Agent-backed conversations."""

import time
from collections.abc import Callable, Iterator
from typing import Any



class ConversationService:
    """Own the conversation use case behind three transport-neutral methods."""

    def __init__(
        self,
        *,
        store_factory: Callable[[], Any],
        route_query: Callable[[str, list[dict]], Any],
        parse_command: Callable[[str], tuple[Any | None, str]],
        direct_route: Any,
        fast_rag_route: Any,
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
        fast_rag_service: Any,
        smart_router: Any | None = None,
    ) -> None:
        self._store_factory = store_factory
        self._route_query = route_query
        self._parse_command = parse_command
        self._direct_route = direct_route
        self._fast_rag_route = fast_rag_route
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
        self._fast_rag_service = fast_rag_service
        self._smart_router = smart_router

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
            forced_route, query = self._parse_command(query)
            if not query:
                raise ValueError("命令后需要提供问题")
            messages = self._messages(query, session_id, store)
            decision = self._smart_router.decide(query, messages[:-1]) if forced_route is None and self._smart_router else None
            route = forced_route or (decision.route if decision is not None else self._route_query(query, messages[:-1]))
            if route == self._direct_route:
                answer = self._direct_answer(self._trim_direct_history(messages))
                history = self._serialize_messages(messages) + [
                    {"role": "assistant", "content": answer, "route": self._direct_route}
                ]
                return answer, store.save(history, session_id), round((time.time() - started) * 1000, 2)

            if route == self._fast_rag_route:
                plan = self._fast_rag_service.prepare(self._trim_direct_history(messages), prefetched_documents=decision.documents if decision else None)
                if not plan.relevant:
                    answer = self._direct_answer(self._trim_direct_history(messages))
                    used_route = self._direct_route
                else:
                    answer = "".join(self._fast_rag_service.stream_answer(messages, plan))
                    answer += self._fast_rag_service.citation_suffix(answer, plan.sources)
                    used_route = self._fast_rag_route
                history = self._serialize_messages(messages) + [
                    {"role": "assistant", "content": answer, "route": used_route}
                ]
                return answer, store.save(history, session_id), round((time.time() - started) * 1000, 2)

            agent_messages = self._model_messages(self._compress_history(messages))
            answer = "".join(self._agent_runtime_factory().stream_messages(
                agent_messages, session_id, selection_context=self._selection_context(decision),
            ))
            history = self._serialize_messages(messages) + [
                {"role": "assistant", "content": answer, "route": self._agent_route}
            ]
            new_session_id = store.save(history, session_id)
        return answer, new_session_id, round((time.time() - started) * 1000, 2)

    def stream(self, query: str, session_id: str | None, stop_event: Any) -> Iterator[dict]:
        store = self._store_factory()
        session_id = session_id or store.allocate()
        with store.lock(session_id):
            yield {"type": "message_start", "data": {"session_id": session_id}}
            started = time.time()
            forced_route, query = self._parse_command(query)
            if not query:
                raise ValueError("命令后需要提供问题")
            messages = self._messages(query, session_id, store)
            decision = self._smart_router.decide(query, messages[:-1]) if forced_route is None and self._smart_router else None
            route = forced_route or (decision.route if decision is not None else self._route_query(query, messages[:-1]))
            if route == self._direct_route:
                yield from self._stream_direct(
                    messages, session_id, stop_event, store, started,
                    performance=self._routing_performance(decision) if decision is not None else None,
                )
                return
            if route == self._fast_rag_route:
                yield from self._stream_fast_rag(messages, session_id, stop_event, store, started, decision=decision)
                return
            yield from self._stream_agent(messages, session_id, stop_event, store, started, decision=decision)

    def _stream_direct(self, messages, session_id, stop_event, store, started, *, performance=None) -> Iterator[dict]:
        parts: list[str] = []
        failed = False
        llm_started = time.perf_counter()
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
            if performance is not None:
                performance["route"] = self._direct_route
                performance.setdefault("stages", {})["llm_ms"] = round(
                    (time.perf_counter() - llm_started) * 1000, 2
                )
                performance["llm_calls"] = 1
                performance["total_ms"] = round((time.time() - started) * 1000, 2)
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
            **({"fast_rag": performance} if performance else {}),
        }}

    def _stream_fast_rag(self, messages, session_id, stop_event, store, started, *, decision=None) -> Iterator[dict]:
        model_messages = self._trim_direct_history(messages)
        plan = self._fast_rag_service.prepare(
            model_messages,
            prefetched_documents=decision.documents if decision is not None else None,
        )
        if not plan.relevant:
            performance = plan.snapshot()
            if decision is not None:
                performance["routing"] = decision.snapshot()
            yield from self._stream_direct(
                messages, session_id, stop_event, store, started,
                performance=performance,
            )
            return

        parts: list[str] = []
        failed = False
        try:
            for chunk in self._fast_rag_service.stream_answer(model_messages, plan):
                if stop_event.is_set():
                    break
                parts.append(chunk)
                yield {"type": "token", "data": {"text": chunk}}
            suffix = self._fast_rag_service.citation_suffix("".join(parts), plan.sources)
            if suffix and not stop_event.is_set():
                parts.append(suffix)
                yield {"type": "token", "data": {"text": suffix}}
        except Exception:
            failed = True
            raise
        finally:
            answer = "".join(parts)
            interrupted = stop_event.is_set() or failed
            assistant = {
                "role": "assistant", "content": answer, "interrupted": interrupted,
                "route": self._fast_rag_route,
            }
            new_session_id = store.save(self._serialize_messages(messages) + [assistant], session_id)
        yield {"type": "sources", "data": {"sources": self._build_sources(answer)}}
        performance = self._fast_rag_service.prepare_snapshot(plan, started)
        if decision is not None:
            performance["routing"] = decision.snapshot()
        yield {"type": "message_end", "data": {
            "session_id": new_session_id,
            "elapsed_ms": round((time.time() - started) * 1000, 2),
            "interrupted": interrupted, "waiting_approval": False,
            "route": self._fast_rag_route, "fast_rag": performance,
        }}

    @staticmethod
    def _routing_performance(decision) -> dict:
        signals = decision.signals
        return {
            "route": decision.route.value,
            "total_ms": float(signals.get("routing_ms", 0.0)),
            "stages": {"routing_ms": float(signals.get("routing_ms", 0.0))},
            "llm_calls": 0,
            "raw_docs_count": int(signals.get("hit_count", 0)),
            "selected_docs_count": 0,
            "context_tokens": 0,
            "relevant": False,
            "routing": decision.snapshot(),
        }

    @staticmethod
    def _selection_context(decision):
        """Translate a route decision once for the ToolSelector seam."""
        if decision is None or getattr(decision, "intent", None) is None:
            return None
        from src.harness import ToolSelectionContext

        intent = decision.intent
        return ToolSelectionContext(
            intent=getattr(intent, "value", str(intent)),
            domain=str(getattr(decision, "domain", "general")),
            side_effect=bool(getattr(decision, "side_effect", False)),
        )

    def _stream_agent(self, messages, session_id, stop_event, store, started, *, decision=None) -> Iterator[dict]:
        tools: list[str] = []
        interrupts: list[Any] = []
        results: list[dict] = []
        parts: list[str] = []
        trace_run_id: str | None = None
        failed = False

        def on_tool(name: str) -> None:
            if name not in tools:
                tools.append(name)

        def on_interrupt(value: Any) -> None:
            interrupts.extend(value if isinstance(value, (list, tuple)) else [value])

        def on_trace_run(run_id: str) -> None:
            nonlocal trace_run_id
            trace_run_id = run_id

        try:
            for chunk in self._agent_runtime_factory().stream_messages(
                self._model_messages(self._compress_history(messages)), session_id,
                on_tool=on_tool, on_interrupt=on_interrupt, on_tool_result=results.append,
                on_trace_run=on_trace_run, selection_context=self._selection_context(decision),
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
            **({"run_id": trace_run_id} if trace_run_id else {}),
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
            command = self._resume_command(decisions or [decision], message)
            for chunk in self._agent_runtime_factory().stream_messages(
                [], session_id, on_tool=on_tool, on_interrupt=on_interrupt,
                on_tool_result=results.append, stream_input=command,
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
            store.save(history + [assistant], session_id)
            yield {"type": "token", "data": {"text": answer}}
            if interrupts:
                yield {"type": "approval_required", "data": {"session_id": session_id, "interrupts": [str(x) for x in interrupts]}}
            if results or interrupts:
                yield {"type": "verification", "data": self._verify_agent_run(answer, results, bool(interrupts))}
            yield {"type": "message_end", "data": {
                "session_id": session_id, "interrupted": bool(stop_event.is_set()), "waiting_approval": bool(interrupts),
            }}
