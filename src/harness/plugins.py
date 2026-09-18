"""Plugin contracts and the context exposed to plugins."""

from dataclasses import dataclass
from typing import Any, Protocol

from src.harness.events import EventBus
from src.harness.tools import ToolRegistry


@dataclass
class PluginContext:
    events: EventBus
    tools: ToolRegistry
    state: dict[str, Any]


class HarnessPlugin(Protocol):
    id: str

    async def start(self, context: PluginContext) -> None: ...

    async def stop(self, context: PluginContext) -> None: ...
