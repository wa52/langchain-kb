import threading
from unittest.mock import patch

from src.agent.query_router import QueryRoute


def test_sync_direct_path_does_not_build_agent_or_compress_history():
    from src.api.services.chat import chat_with_rag

    with (
        patch("src.api.services.chat.load_history", return_value=[]),
        patch("src.api.services.chat.save_history", return_value="sess_direct"),
        patch("src.api.services.chat._direct_answer", return_value="直接回答") as direct,
        patch("src.api.services.chat._get_agent") as get_agent,
        patch("src.api.services.chat._maybe_compress_history") as compress,
    ):
        answer, session_id, _ = chat_with_rag("Python 怎么排序？", None)

    assert answer == "直接回答"
    assert session_id == "sess_direct"
    direct.assert_called_once()
    get_agent.assert_not_called()
    compress.assert_not_called()


def test_stream_direct_path_has_no_tools_or_sources():
    from src.api.services.chat import stream_chat_events

    saved = []
    with (
        patch("src.api.services.chat.allocate_session_id", return_value="sess_direct"),
        patch("src.api.services.chat.load_history", return_value=[]),
        patch("src.api.services.chat.save_history", side_effect=lambda h, s: saved.append(h) or s),
        patch("src.api.services.chat._stream_direct_answer", return_value=iter(["直", "接"])),
        patch("src.api.services.chat._get_agent") as get_agent,
    ):
        events = list(stream_chat_events("Python 怎么排序？", None, threading.Event()))

    assert [event["type"] for event in events] == [
        "message_start", "token", "token", "sources", "message_end"
    ]
    assert events[-2]["data"]["sources"] == []
    assert events[-1]["data"]["route"] == QueryRoute.DIRECT
    assert saved[-1][-1]["route"] == QueryRoute.DIRECT
    get_agent.assert_not_called()


def test_saved_agent_route_is_available_to_follow_up_router():
    from src.api.services.chat import _build_messages

    history = [{"role": "assistant", "content": "资料结果", "route": "agent", "tools": ["retrieve_knowledge"]}]
    with patch("src.api.services.chat.load_history", return_value=history):
        messages = _build_messages("具体呢？", "sess_old")

    assert messages[0]["route"] == "agent"
    assert messages[0]["tools"] == ["retrieve_knowledge"]
    assert messages[-1]["content"] == "具体呢？"
