from src.adapters.agent import LangGraphAgentRuntime
from src.harness import AgentRunTrace, RuleBasedToolSelector, ToolRegistry


class FakeAgent:
    def __init__(self):
        self.thread_ids = []

    def with_config(self, config):
        self.thread_ids.append(config["configurable"]["thread_id"])
        return self


def test_langgraph_adapter_hides_agent_configuration():
    agent = FakeAgent()
    runtime = LangGraphAgentRuntime(
        agent_factory=lambda: agent,
        stream_fn=lambda _agent, messages: [messages[0]["content"], "!"] ,
    )
    assert runtime.run("hi", "session-1") == "hi!"
    assert agent.thread_ids == ["session-1"]


def test_langgraph_adapter_can_cancel_a_stream():
    agent = FakeAgent()
    runtime = LangGraphAgentRuntime(
        agent_factory=lambda: agent,
        stream_fn=lambda _agent, _messages: ["one", "two"],
    )
    stream = runtime.stream("hi", "session-2")
    assert next(stream) == "one"
    runtime.cancel("session-2")
    assert list(stream) == []


def test_langgraph_adapter_forwards_agent_tool_events():
    agent = FakeAgent()
    tools = []

    def stream_fn(_agent, _messages, on_tool=None):
        on_tool("retrieve_knowledge")
        return ["answer"]

    runtime = LangGraphAgentRuntime(agent_factory=lambda: agent, stream_fn=stream_fn)
    assert list(runtime.stream_messages(
        [{"role": "user", "content": "hi"}], "session-3", on_tool=tools.append
    )) == ["answer"]
    assert tools == ["retrieve_knowledge"]


def test_langgraph_adapter_builds_agent_with_selected_tool_catalog():
    registry = ToolRegistry()
    registry.register("retrieve_knowledge", lambda: None, description="检索本地知识库", tags=("knowledge", "search"))
    registry.register("save_material", lambda: None, tags=("knowledge", "write"), read_only=False)
    selected = []

    def factory(*, tool_names=None):
        selected.append(tool_names)
        return FakeAgent()

    runtime = LangGraphAgentRuntime(
        agent_factory=factory,
        stream_fn=lambda _agent, _messages: ["answer"],
        tool_registry=registry,
        tool_selector=RuleBasedToolSelector(max_candidates=3, min_candidates=1),
    )

    trace = AgentRunTrace(run_id="run-4")
    assert list(runtime.stream_messages([{"role": "user", "content": "查询知识库资料"}], "session-4", trace=trace)) == ["answer"]
    assert selected == [("retrieve_knowledge",)]
    assert [event.type for event in trace.events] == ["agent.run.started", "selector.started", "selector.completed", "llm.request", "llm.response", "agent.run.completed"]
