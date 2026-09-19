from contextlib import nullcontext
from types import SimpleNamespace

from src.application.conversation_service import ConversationService


class _Store:
    def __init__(self):
        self.saved = []

    def allocate(self):
        return "fast-session"

    def lock(self, _session_id):
        return nullcontext()

    def load(self, _session_id):
        return []

    def save(self, history, session_id):
        self.saved.append(history)
        return session_id


class _FastRag:
    def __init__(self):
        self.prepared = []
        self.streamed = 0

    def prepare(self, messages, **_kwargs):
        self.prepared.append(messages)
        return SimpleNamespace(
            relevant=True,
            sources=["guide.md"],
            snapshot=lambda: {"route": "fast_rag", "stages": {"search_ms": 1.0}, "llm_calls": 0},
        )

    def stream_answer(self, _messages, _plan):
        self.streamed += 1
        yield "基于资料的回答"

    def citation_suffix(self, _answer, _sources):
        return "\n[来源: guide.md]"

    def prepare_snapshot(self, _plan, _started):
        return {
            "route": "fast_rag", "total_ms": 4.0, "stages": {"search_ms": 1.0, "llm_ms": 2.0},
            "llm_calls": 1, "raw_docs_count": 3, "selected_docs_count": 1,
            "context_tokens": 20, "relevant": True,
        }


class _AgentRuntime:
    def stream_messages(self, _messages, _session_id, **_kwargs):
        yield "Agent 回答"


def _service(fast, *, route=lambda _query, _history: "fast_rag"):
    store = _Store()

    def parse_command(query):
        for command, target in (("/ask ", "direct"), ("/rag ", "fast_rag"), ("/agent ", "agent")):
            if query.startswith(command):
                return target, query[len(command):]
        return None, query

    service = ConversationService(
        store_factory=lambda: store,
        route_query=route,
        parse_command=parse_command,
        direct_route="direct",
        fast_rag_route="fast_rag",
        agent_route="agent",
        direct_answer=lambda _messages: "直接回答",
        stream_direct_answer=lambda _messages: iter(["直接", "回答"]),
        trim_direct_history=lambda messages: messages,
        model_messages=lambda messages: messages,
        compress_history=lambda messages: messages,
        agent_runtime_factory=lambda: _AgentRuntime(),
        serialize_messages=lambda messages: messages,
        build_sources=lambda _answer: [],
        verify_agent_run=lambda *_args: {"complete": True},
        resume_command=lambda *_args: None,
        fast_rag_service=fast,
    )
    return service, store


def test_force_fast_rag_command_skips_agent_and_records_single_llm_plan():
    fast = _FastRag()
    service, store = _service(fast)

    events = list(service.stream("/rag 相机标定", None, SimpleNamespace(is_set=lambda: False)))

    assert fast.prepared[0][-1]["content"] == "相机标定"
    assert fast.streamed == 1
    assert events[-1]["data"]["route"] == "fast_rag"
    assert events[-1]["data"]["fast_rag"]["llm_calls"] == 1
    assert store.saved[-1][-1]["route"] == "fast_rag"


def test_force_direct_command_skips_fast_rag():
    fast = _FastRag()
    service, _store = _service(fast)

    events = list(service.stream("/ask 写一封邮件", None, SimpleNamespace(is_set=lambda: False)))

    assert fast.prepared == []
    assert events[-1]["data"]["route"] == "direct"


def test_force_agent_command_keeps_agent_runtime_path():
    fast = _FastRag()
    service, _store = _service(fast)

    events = list(service.stream("/agent 查网页", None, SimpleNamespace(is_set=lambda: False)))

    assert fast.prepared == []
    assert "Agent 回答" in "".join(event["data"].get("text", "") for event in events)
    assert events[-1]["data"]["route"] == "agent"
