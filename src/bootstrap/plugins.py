"""Concrete infrastructure plugins used by the default application preset."""

import asyncio
from collections.abc import Callable

from src.harness.plugins import PluginContext
from src.resources import ResourceManager


class ResourceManagerPlugin:
    """Adapter that exposes the legacy resource runtime to the Harness kernel."""

    id = "resources"

    def __init__(self, runtime: ResourceManager, echo_fn: Callable[[str], None] = print) -> None:
        self.runtime = runtime
        self.echo_fn = echo_fn

    async def start(self, _context: PluginContext) -> None:
        task = asyncio.create_task(
            asyncio.to_thread(self.runtime.startup, echo_fn=self.echo_fn),
            name="resource-startup",
        )
        self.runtime._startup_task = task
        try:
            await task
        except asyncio.CancelledError:
            self.runtime._shutdown_event.set()
            self.runtime.shutdown(echo_fn=self.echo_fn)
            raise

    async def stop(self, _context: PluginContext) -> None:
        self.runtime.shutdown(echo_fn=self.echo_fn)
