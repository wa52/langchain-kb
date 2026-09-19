"""Scoped tool registry; Agent code depends on this interface, not adapters."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Callable[..., Any]
    description: str = ""
    plugin_id: str = "core"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, name: str, handler: Callable[..., Any], *, description: str = "", plugin_id: str = "core") -> None:
        if not name or name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = ToolSpec(name, handler, description, plugin_id)

    def register_tool(self, tool: Any, *, plugin_id: str = "core") -> None:
        """Register a LangChain-compatible tool without coupling the registry to LangChain."""
        name = getattr(tool, "name", "")
        if not name:
            raise ValueError("Tool must expose a non-empty name")
        self.register(name, tool, description=getattr(tool, "description", ""), plugin_id=plugin_id)

    def langchain_tools(self) -> list[Any]:
        """Return registered tool objects for an agent adapter."""
        return [spec.handler for spec in self._tools.values()]

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
