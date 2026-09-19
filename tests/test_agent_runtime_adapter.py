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
    assert [event.type for event in trace.events] == ["agent.run.started", "selector.started", "selector.completed", "agent.run.completed"]


def test_langgraph_adapter_records_each_model_callback_boundary():
    agent = FakeAgent()

    def stream_fn(_agent, _messages, on_model_start=None, on_model_end=None):
        on_model_start({"llm_call_id": "model-1", "input_messages": 2})
        on_model_end({"llm_call_id": "model-1", "duration_ms": 12.5, "content_length": 4})
        on_model_start({"llm_call_id": "model-2", "input_messages": 4})
        on_model_end({"llm_call_id": "model-2", "duration_ms": 8.5, "content_length": 7})
        return ["answer"]

    runtime = LangGraphAgentRuntime(agent_factory=lambda: agent, stream_fn=stream_fn)
    trace = AgentRunTrace(run_id="run-models")
    assert list(runtime.stream_messages([{"role": "user", "content": "hi"}], "session-models", trace=trace)) == ["answer"]
    assert [call["request"]["llm_call_id"] for call in trace.snapshot()["llm_calls"]] == ["model-1", "model-2"]
    assert [event.type for event in trace.events].count("llm.request") == 2
    assert [event.type for event in trace.events].count("llm.response") == 2


def test_langgraph_adapter_links_retrieval_result_into_trace():
    from src.retrieval.telemetry import RetrievalRecord, retrieval_record_store

    retrieval_record_store.clear()
    record = RetrievalRecord(query="标定")
    record.finish(42.0)
    retrieval_record_store.put(record)

    def stream_fn(_agent, _messages, on_tool_result=None):
        on_tool_result({
            "name": "retrieve_knowledge",
            "tool_call_id": "tool-1",
            "arguments": {"query": "标定"},
            "elapsed_ms": 42.0,
            "status": "success",
            "retrieval": retrieval_record_store.get(record.record_id),
        })
        return ["answer"]

    trace = AgentRunTrace(run_id="run-linked")
    runtime = LangGraphAgentRuntime(agent_factory=lambda: FakeAgent(), stream_fn=stream_fn)
    assert list(runtime.stream_messages([{"role": "user", "content": "标定"}], "session-linked", trace=trace)) == ["answer"]

    event = next(item for item in trace.events if item.type == "tool.call.completed")
    assert event.payload["retrieval"]["run_id"] == "run-linked"
    assert retrieval_record_store.get(record.record_id)["tool_call_id"] == "tool-1"
