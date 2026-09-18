"""Plugin runtime: the composition root for one process."""

import asyncio

from src.harness.events import Event, EventBus
from src.harness.plugins import HarnessPlugin, PluginContext
from src.harness.tools import ToolRegistry


class HarnessRuntime:
    """Own plugin lifecycle and shared registries; transport code stays outside."""

    def __init__(self) -> None:
        self.events = EventBus()
        self.tools = ToolRegistry()
        self.context = PluginContext(self.events, self.tools, {})
        self._plugins: dict[str, HarnessPlugin] = {}
        self._started: list[HarnessPlugin] = []
        self._startup_task: asyncio.Task | None = None
        self._stopped = False

    def register(self, plugin: HarnessPlugin) -> None:
        if plugin.id in self._plugins:
            raise ValueError(f"Plugin already registered: {plugin.id}")
        self._plugins[plugin.id] = plugin

    def plugin_ids(self) -> tuple[str, ...]:
        return tuple(self._plugins)

    async def start(self, *, background: bool = False) -> asyncio.Task | None:
        if self._startup_task is not None and not self._startup_task.done() and asyncio.current_task() is not self._startup_task:
            return self._startup_task
        self._stopped = False
        self._startup_task = asyncio.create_task(self._start_all(), name="harness-startup")
        if background:
            return self._startup_task
        await self._startup_task
        return None

    async def _start_all(self) -> None:
        try:
            for plugin in self._plugins.values():
                await plugin.start(self.context)
                self._started.append(plugin)
            self.events.publish(Event("runtime.ready", {"plugins": list(self.plugin_ids())}))
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._startup_task is not None and not self._startup_task.done():
            self._startup_task.cancel()
            try:
                await self._startup_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        for plugin in reversed(self._started):
            try:
                await plugin.stop(self.context)
            finally:
                self.tools.unregister_plugin(plugin.id)
        self._started.clear()
        self.events.publish(Event("runtime.stopped"))
