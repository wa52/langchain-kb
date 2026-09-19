import asyncio

from src.harness import Event, EventBus, HarnessRuntime, SessionLog, ToolRegistry


def test_event_bus_and_tool_registry_are_isolated():
    seen = []
    bus = EventBus()
    bus.subscribe("turn.token", lambda event: seen.append(event.payload["text"]))
    bus.publish(Event("turn.token", {"text": "hello"}))

    tools = ToolRegistry()
    tools.register("sum", lambda left, right: left + right, plugin_id="math")
    assert tools.call("sum", left=2, right=3) == 5
    tools.unregister_plugin("math")
    assert tools.names() == ()
    assert seen == ["hello"]


def test_tool_registry_exposes_langchain_tools_without_framework_imports():
    class Tool:
        name = "demo"
        description = "demo tool"

        def invoke(self, payload):
            return payload["value"]

    tools = ToolRegistry()
    tool = Tool()
    tools.register_tool(tool, plugin_id="demo-plugin")
    assert tools.names() == ("demo",)
    assert tools.langchain_tools() == [tool]
    assert tools.call("demo", value=3) == 3


def test_tool_catalog_exposes_metadata_and_filters_disabled_tools():
    tools = ToolRegistry()
    tools.register("search", lambda: None, source="local", tags=("knowledge", "search"), retryable=True)
    tools.register("issue", lambda: None, source="mcp", server_id="github", tags=("github", "write"), risk_level="medium", read_only=False, enabled=False)
    assert [spec.name for spec in tools.catalog(tags=("knowledge",))] == ["search"]
    assert tools.catalog(source="mcp", include_disabled=True)[0].server_id == "github"
    assert tools.langchain_tools() == [tools.get("search").handler]


def test_session_log_is_append_only_snapshot():
    log = SessionLog("session-1")
    first = log.append("user.message", text="hi")
    log.append("assistant.message", text="hello")
    snapshot = log.snapshot()
    assert snapshot == (first, snapshot[1])
    assert [event.type for event in snapshot] == ["user.message", "assistant.message"]


def test_runtime_starts_and_stops_plugins_in_order():
    calls = []

    class Plugin:
        def __init__(self, plugin_id):
            self.id = plugin_id

        async def start(self, _context):
            calls.append(f"start:{self.id}")

        async def stop(self, _context):
            calls.append(f"stop:{self.id}")

    async def run():
        runtime = HarnessRuntime()
        runtime.register(Plugin("one"))
        runtime.register(Plugin("two"))
        await runtime.start()
        await runtime.stop()

    asyncio.run(run())
    assert calls == ["start:one", "start:two", "stop:two", "stop:one"]
