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
        return self.get(name).handler(**kwargs)
