"""Small transport-neutral execution trace primitives."""

from dataclasses import dataclass, field
from typing import Any

from src.harness.execution import ToolResult
from src.harness.events import Event, EventBus


@dataclass
class AgentRunTrace:
    run_id: str = ""
    query: str = ""
    selected_tools: tuple[str, ...] = ()
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    event_bus: EventBus | None = field(default=None, repr=False, compare=False)

    def emit(self, event_type: str, **payload: Any) -> None:
        event = Event(event_type, {"run_id": self.run_id, **payload})
        self.events.append(event)
        if self.event_bus is not None:
            self.event_bus.publish(event)

    def record(self, result: ToolResult, *, arguments: dict[str, Any] | None = None) -> None:
        self.emit("tool.call.completed", tool_name=result.tool_name, success=result.success, error_type=result.error_type, elapsed_ms=result.elapsed_ms, retry_count=result.retry_count)
        self.tool_calls.append({
            "tool_name": result.tool_name,
            "arguments": arguments or {},
            "success": result.success,
            "error_type": result.error_type,
            "elapsed_ms": result.elapsed_ms,
            "retry_count": result.retry_count,
        })

    def record_llm_request(self, **payload: Any) -> None:
        self.emit("llm.request", **payload)
        self.llm_calls.append({"request": dict(payload)})

    def record_llm_response(self, **payload: Any) -> None:
        self.emit("llm.response", **payload)
        for call in reversed(self.llm_calls):
            if "response" not in call:
                call["response"] = dict(payload)
                break

    def snapshot(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "query": self.query, "selected_tools": list(self.selected_tools), "llm_calls": list(self.llm_calls), "tool_calls": list(self.tool_calls), "events": [{"type": e.type, "payload": e.payload, "created_at": e.created_at} for e in self.events]}
