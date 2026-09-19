"""Small transport-neutral execution trace primitives."""

from dataclasses import dataclass, field
from typing import Any

from src.harness.execution import ToolResult


@dataclass
class AgentRunTrace:
    query: str = ""
    selected_tools: tuple[str, ...] = ()
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def record(self, result: ToolResult, *, arguments: dict[str, Any] | None = None) -> None:
        self.tool_calls.append({
            "tool_name": result.tool_name,
            "arguments": arguments or {},
            "success": result.success,
            "error_type": result.error_type,
            "elapsed_ms": result.elapsed_ms,
            "retry_count": result.retry_count,
        })

    def snapshot(self) -> dict[str, Any]:
        return {"query": self.query, "selected_tools": list(self.selected_tools), "tool_calls": list(self.tool_calls)}
