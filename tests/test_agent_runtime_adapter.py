from src.adapters.agent import LangGraphAgentRuntime


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
