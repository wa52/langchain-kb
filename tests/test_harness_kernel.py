import asyncio

from src.harness import AgentRunTrace, Event, EventBus, ExecutionPolicy, HarnessRuntime, JevToolSelector, RuleBasedToolSelector, SessionLog, ToolExecutor, ToolRegistry, TraceStore


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


def test_tool_selector_uses_metadata_and_keeps_write_tools_out_of_fallback():
    tools = ToolRegistry()
    tools.register("retrieve_knowledge", lambda: None, description="检索本地知识库文档", tags=("knowledge", "search"), retryable=True)
    tools.register("retrieve_graph", lambda: None, description="查询图谱关系", tags=("graph", "knowledge", "search"), retryable=True)
    tools.register("github_create_issue", lambda: None, source="mcp", server_id="github", tags=("github", "mcp", "write"), risk_level="medium", read_only=False)
    tools.register("save_material", lambda: None, description="保存研究资料", tags=("knowledge", "write"), risk_level="medium", read_only=False)

    selected = RuleBasedToolSelector(max_candidates=3, min_candidates=2).select("帮我查询知识库里的 Halcon 文档", tools.catalog())

    assert selected[0].spec.name == "retrieve_knowledge"
    assert {candidate.spec.name for candidate in selected} == {"retrieve_knowledge", "retrieve_graph"}
    assert all(candidate.spec.read_only for candidate in selected)


def test_tool_selector_finds_mcp_server_from_query_keyword():
    tools = ToolRegistry()
    tools.register("retrieve_knowledge", lambda: None, tags=("knowledge", "search"))
    tools.register("github_create_issue", lambda: None, source="mcp", server_id="github", tags=("github", "mcp", "write"), risk_level="medium", read_only=False)

    selected = RuleBasedToolSelector(max_candidates=3, min_candidates=1).select_names("帮我在 GitHub 创建 issue", tools.catalog())

    assert selected == ("github_create_issue",)


def test_jev_selector_ranks_recalled_tools_and_falls_back_without_key():
    tools = ToolRegistry()
    tools.register("retrieve_knowledge", lambda: None, description="search knowledge", tags=("knowledge", "search"))
    tools.register("retrieve_graph", lambda: None, description="search graph", tags=("graph", "search"))
    fallback = RuleBasedToolSelector(max_candidates=4, min_candidates=1)
    response = {"answers": {"tool": {"probabilities": {"retrieve_knowledge": 0.2, "retrieve_graph": 0.8}}}}
    selector = JevToolSelector(fallback, api_key="test", request=lambda _payload, _key: response)
    assert selector.select_names("search knowledge", tools.catalog()) == ("retrieve_graph", "retrieve_knowledge")


def test_tool_executor_retries_only_read_only_retryable_tools():
    calls = []
    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary")
        return "ok"
    spec = ToolRegistry()
    spec.register("search", flaky, retryable=True, read_only=True)
    result = ToolExecutor().execute(spec.get("search"), {})
    assert result.success and result.data == "ok" and result.retry_count == 1


def test_tool_executor_requires_approval_for_high_risk_tool():
    registry = ToolRegistry()
    registry.register("delete", lambda: "done", risk_level="high", read_only=False)
    result = ToolExecutor().execute(registry.get("delete"), {})
    assert not result.success and result.error_type == "APPROVAL_REQUIRED"


def test_agent_run_trace_records_tool_result_summary():
    trace = AgentRunTrace(query="search docs", selected_tools=("search",))
    from src.harness import ToolResult
    trace.record(ToolResult(True, "search", data="ok", elapsed_ms=4.2))
    assert trace.snapshot()["selected_tools"] == ["search"]


def test_tool_executor_emits_trace_events():
    trace = AgentRunTrace(run_id="run-1")
    registry = ToolRegistry()
    registry.register("search", lambda query: query, read_only=True)
    result = ToolExecutor(trace=trace).execute(registry.get("search"), {"query": "docs"})
    assert result.success
    assert [event.type for event in trace.events] == ["tool.call.started", "tool.call.completed"]


def test_trace_store_reads_completed_runs_by_id():
    store = TraceStore(max_runs=2)
    trace = AgentRunTrace(run_id="run-1", query="hello")
    store.put(trace)
    assert store.get("run-1")["query"] == "hello"


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
