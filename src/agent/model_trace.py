"""LangChain-compatible callbacks used to observe model invocations."""

from __future__ import annotations

import time

from langchain_core.callbacks import BaseCallbackHandler


class ModelTraceCallbacks(BaseCallbackHandler):
    """Bridge LangChain model callbacks to transport-neutral trace hooks.

    Inheriting from :class:`BaseCallbackHandler` is intentional: LangChain's
    callback manager reads standard handler fields such as ``raise_error``
    while it dispatches model events.
    """

    def __init__(self, on_start=None, on_end=None, on_error=None):
        super().__init__()
        self._on_start = on_start
        self._on_end = on_end
        self._on_error = on_error
        self._started: dict[str, float] = {}

    @staticmethod
    def _run_key(run_id) -> str:
        return str(run_id)

    @staticmethod
    def _message_count(messages) -> int:
        if not messages:
            return 0
        if isinstance(messages, list) and messages and isinstance(messages[0], list):
            return sum(len(group) for group in messages)
        return len(messages) if isinstance(messages, list) else 0

    @staticmethod
    def _response_details(response) -> tuple[bool, list[str], int]:
        tool_names: list[str] = []
        content_length = 0
        for generation in getattr(response, "generations", []) or []:
            for item in generation if isinstance(generation, list) else [generation]:
                message = getattr(item, "message", None) or getattr(item, "text", item)
                content = getattr(message, "content", "") or ""
                content_length += len(str(content))
                for call in getattr(message, "tool_calls", None) or []:
                    name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                    if name:
                        tool_names.append(str(name))
        return bool(tool_names), tool_names, content_length

    def on_chat_model_start(self, _serialized, messages, *, run_id, **_kwargs):
        key = self._run_key(run_id)
        self._started[key] = time.perf_counter()
        if self._on_start is not None:
            self._on_start({
                "llm_call_id": key,
                "input_messages": self._message_count(messages),
            })

    def on_llm_end(self, response, *, run_id, **_kwargs):
        key = self._run_key(run_id)
        started = self._started.pop(key, time.perf_counter())
        has_tool_calls, tool_names, content_length = self._response_details(response)
        if self._on_end is not None:
            self._on_end({
                "llm_call_id": key,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "has_tool_calls": has_tool_calls,
                "tool_calls": tool_names,
                "content_length": content_length,
            })

    def on_llm_error(self, error, *, run_id, **_kwargs):
        key = self._run_key(run_id)
        started = self._started.pop(key, time.perf_counter())
        if self._on_error is not None:
            self._on_error({
                "llm_call_id": key,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": str(error),
            })
