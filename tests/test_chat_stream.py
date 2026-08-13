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
        assert sources == [{"source": "guide.md", "chunk_id": "", "excerpt": None}]

    def test_history_saved_with_interrupted_flag_false(self, client):
        saved = []

        def fake_save(history, session_id):
            saved.append(history)
            return "sess_x"

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["ok"]),
            patch("src.api.services.chat.save_history", side_effect=fake_save),
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


class TestChatStreamErrors:
    def test_stream_error_emits_error_event(self, client):
        def boom(agent, messages):
            raise RuntimeError("llm unavailable")

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", side_effect=boom),
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
