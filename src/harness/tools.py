"""Scoped tool registry; Agent code depends on this interface, not adapters."""

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


ToolSource = Literal["local", "mcp", "plugin"]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Callable[..., Any]
    description: str = ""
    plugin_id: str = "core"
    source: ToolSource = "local"
    server_id: str | None = None
    tags: tuple[str, ...] = ()
    risk_level: RiskLevel = "low"
    timeout_seconds: float | None = None
    retryable: bool = False
    read_only: bool = True
    input_schema: dict[str, Any] | None = None
    enabled: bool = True


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, name: str, handler: Callable[..., Any], *, description: str = "", plugin_id: str = "core", source: ToolSource = "local", server_id: str | None = None, tags: tuple[str, ...] = (), risk_level: RiskLevel = "low", timeout_seconds: float | None = None, retryable: bool = False, read_only: bool = True, input_schema: dict[str, Any] | None = None, enabled: bool = True) -> None:
        if not name or name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = ToolSpec(name, handler, description, plugin_id, source, server_id, tuple(sorted(set(tags))), risk_level, timeout_seconds, retryable, read_only, input_schema, enabled)

    def register_tool(self, tool: Any, *, plugin_id: str = "core", source: ToolSource = "local", server_id: str | None = None, tags: tuple[str, ...] = (), risk_level: RiskLevel = "low", timeout_seconds: float | None = None, retryable: bool = False, read_only: bool = True, enabled: bool = True) -> None:
        """Register a LangChain-compatible tool without coupling the registry to LangChain."""
        name = getattr(tool, "name", "")
        if not name:
            raise ValueError("Tool must expose a non-empty name")
        schema = getattr(tool, "args_schema", None)
        self.register(name, tool, description=getattr(tool, "description", ""), plugin_id=plugin_id, source=source, server_id=server_id, tags=tags, risk_level=risk_level, timeout_seconds=timeout_seconds, retryable=retryable, read_only=read_only, input_schema=getattr(schema, "model_json_schema", lambda: None)(), enabled=enabled)

    def langchain_tools(self) -> list[Any]:
        """Return registered tool objects for an agent adapter."""
        return [spec.handler for spec in self._tools.values() if spec.enabled]

    def catalog(self, *, source: ToolSource | None = None, tags: tuple[str, ...] = (), include_disabled: bool = False) -> tuple[ToolSpec, ...]:
        """Return discoverable metadata without exposing tool handlers."""
        wanted = set(tags)
        return tuple(spec for spec in self._tools.values() if (include_disabled or spec.enabled) and (source is None or spec.source == source) and wanted.issubset(spec.tags))

    def unregister_plugin(self, plugin_id: str) -> None:
        self._tools = {name: spec for name, spec in self._tools.items() if spec.plugin_id != plugin_id}

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def call(self, name: str, **kwargs: Any) -> Any:
        handler = self.get(name).handler
        invoke = getattr(handler, "invoke", None)
        return invoke(kwargs) if invoke is not None else handler(**kwargs)
