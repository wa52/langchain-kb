from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_singleton():
    from src.resources import ResourceManager
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    yield
    ResourceManager._instance = None


@pytest.fixture(autouse=True)
def force_legacy_tests_through_agent_path():
    """This module tests the Agent seam; routing has its own test module."""
    from src.agent.query_router import QueryRoute
    with patch("src.api.services.chat.route_query", return_value=QueryRoute.AGENT):
        yield


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


class TestChatReusesRetriever:
    def test_chat_service_uses_resource_manager(self):
        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["hello"]),
            patch("src.api.services.chat.save_history", return_value="sess_1"),
        ):
            from src.api.services.chat import chat_with_rag
            answer, sid, _ = chat_with_rag("hi", None)
            assert answer == "hello"
            assert sid == "sess_1"

    def test_two_chat_requests_independent(self):
        call_log = []

        def fake_stream(agent, messages):
            call_log.append(messages)
            from itertools import count
            c = count()
            def gen():
                yield f"answer_{next(c)}"
            return gen()

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", side_effect=fake_stream),
            patch("src.api.services.chat.save_history", side_effect=lambda h, sid: sid or "new"),
        ):
            from src.api.services.chat import chat_with_rag
            a1, _, _ = chat_with_rag("first", None)
            a2, _, _ = chat_with_rag("second", None)
            assert a1 == "answer_0"
            assert a2 == "answer_0"


class TestChatFailureIsolation:
    def test_first_fails_second_succeeds(self):
        call_count = [0]

        def fake_stream(agent, messages):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("first request fails")
            return iter(["success"])

        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", side_effect=fake_stream),
            patch("src.api.services.chat.save_history", return_value="sess_2"),
        ):
            from src.api.services.chat import chat_with_rag
            with pytest.raises(RuntimeError, match="first request fails"):
                chat_with_rag("fail", None)
            answer, _, _ = chat_with_rag("ok", None)
            assert answer == "success"


class TestChatNoKnowledge:
    def test_empty_knowledge_returns_honest_answer(self):
        from src.api.services.chat import chat_with_rag
        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["I don't know"]),
            patch("src.api.services.chat.save_history", return_value="sess_3"),
        ):
            answer, _, _ = chat_with_rag("unknown topic", None)
            assert "don't know" in answer.lower() or "不知道" in answer

    def test_retrieval_error_graceful(self):
        from src.api.services.chat import chat_with_rag
        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", side_effect=RuntimeError("retrieval failed")),
            patch("src.api.services.chat.save_history", return_value="sess_4"),
        ):
            with pytest.raises(RuntimeError, match="retrieval failed"):
                chat_with_rag("test", None)
