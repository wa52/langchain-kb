"""Streaming chat API tests at the HTTP seam.

Covers the POST /api/v1/chat/stream SSE contract: event ordering,
token accumulation, sources extraction, error events, interrupted
history persistence, and session continuation.
"""

import json
import threading
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_singleton():
    from src.resources import ResourceManager
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    yield
    ResourceManager._instance = None


@pytest.fixture
def rm():
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    rm._initialized = True
    rm.vector_store = MagicMock()
    rm.graph = MagicMock()
    rm.llm = MagicMock()
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    return TestClient(create_app())


def _patch_stream(stream_result, save_return="sess_stream", load_return=None):
    stack = ExitStack()
    stack.enter_context(patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()))
    stack.enter_context(patch("src.api.services.chat.stream_rag_response", return_value=stream_result))
    stack.enter_context(patch("src.api.services.chat.save_history", return_value=save_return))
    stack.enter_context(patch("src.api.services.chat.load_history", return_value=load_return))
    stack.enter_context(patch("src.api.services.chat.allocate_session_id", return_value="sess_new"))
    stack.enter_context(patch("src.api.services.chat._source_lookup",
                              return_value={"chunk_id": "", "excerpt": None}))
    return stack


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse SSE 'event:' / 'data:' blocks into (type, data) tuples."""
    events = []
    for block in text.split("\n\n"):
        lines = [l for l in block.splitlines() if l.startswith(("event:", "data:"))]
        if not lines:
            continue
        ev = None
        data = None
        for line in lines:
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        if ev is not None:
            events.append((ev, data))
    return events


class TestChatStreamSSEFraming:
    def test_stream_emits_events_in_order(self, client):
        with _patch_stream(["Hello", " ", "world"]):
            resp = client.post("/api/v1/chat/stream", json={"query": "hi"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.text)
        types = [e[0] for e in events]
        assert types[0] == "message_start"
        assert types[-1] == "message_end"
        assert "token" in types
        assert "sources" in types
        text = "".join(e[1]["text"] for e in events if e[0] == "token")
        assert text == "Hello world"

    def test_message_end_carries_session_and_not_interrupted(self, client):
        with _patch_stream(["done"], save_return="sess_stream"):
            resp = client.post("/api/v1/chat/stream", json={"query": "hi"})
        events = _parse_sse(resp.text)
        end = [e for e in events if e[0] == "message_end"][0][1]
        assert end["session_id"] == "sess_stream"
        assert end["interrupted"] is False
        assert isinstance(end["elapsed_ms"], (int, float))

    def test_sources_are_extracted_from_answer(self, client):
        with _patch_stream(["根据资料 [来源: guide.md] 说明。"]):
            resp = client.post("/api/v1/chat/stream", json={"query": "hi"})
        events = _parse_sse(resp.text)
        sources = [e for e in events if e[0] == "sources"][0][1]["sources"]
        assert len(sources) == 1
        assert sources[0]["source"] == "guide.md"
        assert sources[0]["chunk_id"] == ""
        assert sources[0]["excerpt"] is None
        assert isinstance(sources[0]["hit_chain"], list)

    def test_sources_are_enriched_with_chunk_and_excerpt(self, client):
        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response",
                  return_value=["根据资料 [来源: guide.md] 说明。"]),
            patch("src.api.services.chat.save_history", return_value="sess_x"),
            patch("src.api.services.chat.load_history", return_value=None),
            patch("src.api.services.chat.allocate_session_id", return_value="sess_new"),
            patch("src.api.services.chat._source_lookup",
                  return_value={"chunk_id": "chunk-42", "excerpt": "标定方法要点…"}),
        ):
            resp = client.post("/api/v1/chat/stream", json={"query": "hi"})
        events = _parse_sse(resp.text)
        sources = [e for e in events if e[0] == "sources"][0][1]["sources"]
        assert sources[0]["chunk_id"] == "chunk-42"
        assert sources[0]["excerpt"] == "标定方法要点…"

    def test_source_lookup_falls_back_to_empty(self):
        from src.api.services.chat import _source_lookup
        with patch("src.vector_store.chroma_client.get_vector_store",
                   side_effect=RuntimeError("no store")):
            assert _source_lookup("missing.md") == {"chunk_id": "", "excerpt": None}

    def test_source_lookup_falls_back_to_basename_match(self):
        from src.api.services.chat import _source_lookup
        with (
            patch("src.api.services.chat._query_source",
                  side_effect=lambda n: {"chunk_id": "", "excerpt": None}
                  if n == "dir.md"
                  else {"chunk_id": "chunk-9", "excerpt": "子目录文档摘录…"}),
            patch("src.api.services.chat._basename_to_source", return_value="sub/dir.md"),
        ):
            result = _source_lookup("dir.md")
        assert result == {"chunk_id": "chunk-9", "excerpt": "子目录文档摘录…"}

    def test_source_lookup_skips_basename_fallback_for_pathlike(self):
        from src.api.services.chat import _source_lookup
        with (
            patch("src.api.services.chat._query_source",
                  return_value={"chunk_id": "", "excerpt": None}),
            patch("src.api.services.chat._basename_to_source",
                  return_value="should-not-be-used") as mock_base,
        ):
            result = _source_lookup("sub/dir.md")
        assert result == {"chunk_id": "", "excerpt": None}
        mock_base.assert_not_called()

    def test_basename_to_source_builds_index(self):
        import src.api.services.chat as chat_mod
        fake_col = MagicMock()
        fake_col.get.side_effect = [
            {
                "metadatas": [{"source": "a/b.md"}, {"source": "top.md"}, {"source": "c/b.md"}],
            },
            {"metadatas": []},
        ]
        fake_store = MagicMock()
        fake_store._collection = fake_col
        with (
            patch.object(chat_mod, "_basename_index", None),
            patch.object(chat_mod, "_basename_index_ts", 0.0),
            patch("src.vector_store.chroma_client.get_vector_store", return_value=fake_store),
        ):
            result = chat_mod._basename_to_source("b.md")
        assert result == "a/b.md"

    def test_history_saved_with_interrupted_flag_false(self, client):
        saved = []

        def fake_save(history, session_id):
            saved.append(history)
            return "sess_x"

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["ok"]),
            patch("src.api.services.chat.save_history", side_effect=fake_save),
            patch("src.api.services.chat.allocate_session_id", return_value="sess_new"),
            patch("src.api.services.chat.load_history", return_value=None),
        ):
            resp = client.post("/api/v1/chat/stream", json={"query": "hi"})
        assert resp.status_code == 200
        history = saved[0]
        assert history[-1]["role"] == "assistant"
        assert history[-1]["content"] == "ok"
        assert history[-1]["interrupted"] is False

    def test_empty_query_rejected(self, client):
        resp = client.post("/api/v1/chat/stream", json={"query": ""})
        assert resp.status_code == 422


class TestChatStreamToolEvent:
    def test_tool_event_emitted_when_agent_uses_tools(self, client):
        def fake_stream(agent, messages, on_tool=None):
            if on_tool:
                on_tool("retrieve_knowledge")
                on_tool("retrieve_graph")
                on_tool("retrieve_knowledge")  # duplicate id deduped by service
            yield "answer"

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", side_effect=fake_stream),
            patch("src.api.services.chat.save_history", return_value="sess_x"),
            patch("src.api.services.chat.allocate_session_id", return_value="sess_new"),
            patch("src.api.services.chat.load_history", return_value=None),
        ):
            resp = client.post("/api/v1/chat/stream", json={"query": "hi"})
        events = _parse_sse(resp.text)
        types = [e[0] for e in events]
        assert "tool" in types
        idx = types.index("tool")
        # tool is emitted after tokens, before sources / message_end
        assert types[:idx] == ["message_start", "token"]
        assert types.index("sources") > idx
        tool_events = [e for e in events if e[0] == "tool"]
        assert tool_events[-1][1]["tools"] == ["retrieve_knowledge", "retrieve_graph"]

    def test_no_tool_event_without_tool_calls(self, client):
        with _patch_stream(["plain answer"]):
            resp = client.post("/api/v1/chat/stream", json={"query": "hi"})
        events = _parse_sse(resp.text)
        types = [e[0] for e in events]
        assert "tool" not in types


class TestChatStreamErrors:
    def test_stream_error_emits_error_event(self, client):
        def boom(agent, messages, on_tool=None):
            raise RuntimeError("llm unavailable")

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", side_effect=boom),
            patch("src.api.services.chat.allocate_session_id", return_value="sess_new"),
            patch("src.api.services.chat.load_history", return_value=None),
        ):
            resp = client.post("/api/v1/chat/stream", json={"query": "hi"})
        events = _parse_sse(resp.text)
        errors = [e for e in events if e[0] == "error"]
        assert errors
        assert "llm unavailable" in errors[0][1]["error"]


class TestChatStreamContinuation:
    def test_loads_history_for_session(self, client):
        with _patch_stream(["ok"], save_return="sess_old",
                           load_return=[{"role": "user", "content": "prev"}]):
            resp = client.post("/api/v1/chat/stream", json={
                "query": "follow",
                "session_id": "sess_old",
            })
        events = _parse_sse(resp.text)
        end = [e for e in events if e[0] == "message_end"][0][1]
        assert end["session_id"] == "sess_old"


class TestChatStreamSessionAllocation:
    def test_brand_new_session_preallocates_id(self, client):
        saved = []

        def fake_save(history, session_id):
            saved.append((history, session_id))
            return session_id

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["ok"]),
            patch("src.api.services.chat.save_history", side_effect=fake_save),
            patch("src.api.services.chat.allocate_session_id", return_value="sess_new"),
        ):
            resp = client.post("/api/v1/chat/stream", json={"query": "hi"})
        events = _parse_sse(resp.text)
        start = [e for e in events if e[0] == "message_start"][0][1]
        end = [e for e in events if e[0] == "message_end"][0][1]
        assert start["session_id"] == "sess_new"
        assert end["session_id"] == "sess_new"
        assert saved[0][1] == "sess_new"

    def test_continuation_keeps_given_id_in_message_start(self, client):
        with _patch_stream(["ok"], save_return="sess_old",
                           load_return=[{"role": "user", "content": "prev"}]):
            resp = client.post("/api/v1/chat/stream", json={
                "query": "follow",
                "session_id": "sess_old",
            })
        events = _parse_sse(resp.text)
        start = [e for e in events if e[0] == "message_start"][0][1]
        assert start["session_id"] == "sess_old"

    def test_interrupted_brand_new_session_uses_preallocated_id(self):
        from src.api.services.chat import stream_chat_events
        stop = threading.Event()
        saved = []

        def fake_save(history, session_id):
            saved.append((history, session_id))
            return session_id

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["part1"]),
            patch("src.api.services.chat.save_history", side_effect=fake_save),
            patch("src.api.services.chat.allocate_session_id", return_value="sess_new"),
        ):
            gen = stream_chat_events("hi", None, stop)
            start = next(gen)["data"]
            next(gen)
            stop.set()
            events = list(gen)
        end = events[-1]["data"]
        assert start["session_id"] == "sess_new"
        assert end["session_id"] == "sess_new"
        assert end["interrupted"] is True
        assert saved[0][1] == "sess_new"


class TestChatStreamServiceInterrupted:
    def test_stop_before_stream_saves_empty_interrupted(self):
        from src.api.services.chat import stream_chat_events
        stop = threading.Event()
        stop.set()
        saved = []

        def fake_save(history, session_id):
            saved.append(history)
            return "sess_partial"

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["partial", " text"]),
            patch("src.api.services.chat.save_history", side_effect=fake_save),
            patch("src.api.services.chat.allocate_session_id", return_value="sess_new"),
        ):
            events = list(stream_chat_events("hi", None, stop))
        types = [e["type"] for e in events]
        assert types == ["message_start", "sources", "message_end"]
        end = events[-1]["data"]
        assert end["interrupted"] is True
        assert saved[0][-1]["interrupted"] is True
        assert saved[0][-1]["content"] == ""

    def test_stop_mid_stream_keeps_partial_text(self):
        from src.api.services.chat import stream_chat_events
        stop = threading.Event()
        saved = []

        def fake_save(history, session_id):
            saved.append(history)
            return "sess_partial"

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["part1", "part2"]),
            patch("src.api.services.chat.save_history", side_effect=fake_save),
            patch("src.api.services.chat.allocate_session_id", return_value="sess_new"),
        ):
            gen = stream_chat_events("hi", None, stop)
            assert next(gen)["type"] == "message_start"
            assert next(gen)["type"] == "token"
            assert next(gen)["type"] == "token"
            stop.set()
            rest = list(gen)
        types = [e["type"] for e in rest]
        assert "token" not in types
        assert types[-1] == "message_end"
        assert rest[-1]["data"]["interrupted"] is True
        assert saved[0][-1]["content"] == "part1part2"
        assert saved[0][-1]["interrupted"] is True
