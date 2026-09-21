import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from unittest.mock import Mock

from src.feishu.bot import (
    _MessageDeduper,
    _message_text,
    _sender_key,
    ask_knowledge_base,
    process_incoming_message,
)
from src.feishu.session_map import SessionStore


def make_message(
    message_type="text",
    content=None,
    message_id="msg_1",
    chat_id="chat_1",
    chat_type="p2p",
    open_id="ou_1",
):
    message = SimpleNamespace(
        message_type=message_type,
        content=content,
        message_id=message_id,
        chat_id=chat_id,
        chat_type=chat_type,
    )
    sender = SimpleNamespace(sender_id=SimpleNamespace(open_id=open_id))
    return SimpleNamespace(event=SimpleNamespace(message=message, sender=sender))


class TestMessageParsing:
    def test_message_text(self):
        event = make_message(content=json.dumps({"text": "什么是RAG？"}))
        assert _message_text(event) == "什么是RAG？"

    def test_message_text_ignores_non_text(self):
        event = make_message(message_type="image", content=json.dumps({"image_key": "x"}))
        assert _message_text(event) is None

    def test_message_text_handles_bad_json(self):
        event = make_message(content="not json")
        assert _message_text(event) is None

    def test_sender_key_prefers_open_id(self):
        event = make_message(open_id="ou_42")
        assert _sender_key(event) == "ou_42"

    def test_sender_key_falls_back_to_chat_id(self):
        event = make_message(open_id=None)
        assert _sender_key(event) == "chat_1"


class TestMessageDeduper:
    def test_duplicate_event_is_ignored(self):
        deduper = _MessageDeduper(ttl=60, max_entries=2)
        assert deduper.seen("msg_1") is False
        assert deduper.seen("msg_1") is True

    def test_oldest_event_is_evicted_when_bounded(self):
        deduper = _MessageDeduper(ttl=60, max_entries=2)
        deduper.seen("msg_1")
        deduper.seen("msg_2")
        deduper.seen("msg_3")
        assert deduper.seen("msg_1") is False


class TestStreamingMessageUpdater:
    def test_slow_remote_update_does_not_block_submit(self):
        from src.feishu.bot import _StreamingMessageUpdater

        sent = []

        def slow_update(text):
            time.sleep(0.15)
            sent.append(text)

        updater = _StreamingMessageUpdater(slow_update, interval_seconds=0.01)
        started = time.perf_counter()
        updater.submit("一")
        updater.submit("一个更完整的回答")
        elapsed_ms = (time.perf_counter() - started) * 1000
        updater.finish("一个更完整的回答")
        time.sleep(0.2)

        assert elapsed_ms < 30
        assert sent[-1] == "一个更完整的回答"

    def test_stream_reply_keeps_consuming_sse_while_updates_are_slow(self):
        from src.feishu.bot import FeishuBot

        bot = FeishuBot.__new__(FeishuBot)
        bot._reply = Mock(return_value="placeholder")
        updates = []

        def slow_update(_message_id, text):
            time.sleep(0.15)
            updates.append(text)

        bot._update_message = slow_update
        events = iter([
            ("token", {"text": "第"}),
            ("token", {"text": "一段"}),
            ("message_end", {"session_id": "session_1"}),
        ])
        with patch("src.feishu.bot.stream_knowledge_base", return_value=events):
            started = time.perf_counter()
            session_id = bot._stream_reply("source", "chat", "p2p", "问题", None)
            elapsed_ms = (time.perf_counter() - started) * 1000

        assert session_id == "session_1"
        assert elapsed_ms < 50
        for _ in range(20):
            if updates and updates[-1] == "第一段":
                break
            time.sleep(0.02)
        assert updates[-1] == "第一段"

    def test_short_stream_sends_only_the_final_feishu_update(self):
        from src.feishu.bot import FeishuBot

        bot = FeishuBot.__new__(FeishuBot)
        bot._reply = Mock(return_value="placeholder")
        updates = []
        bot._update_message = lambda _message_id, text: updates.append(text)
        events = iter([
            ("token", {"text": "短"}),
            ("token", {"text": "回答"}),
            ("message_end", {"session_id": "session_1"}),
        ])
        with patch("src.feishu.bot.stream_knowledge_base", return_value=events):
            bot._stream_reply("source", "chat", "p2p", "问题", None)

        for _ in range(20):
            if updates:
                break
            time.sleep(0.02)
        assert updates == ["短回答"]

    def test_incomplete_sse_never_publishes_a_partial_answer(self):
        from src.feishu.bot import FeishuBot

        bot = FeishuBot.__new__(FeishuBot)
        bot._reply = Mock(return_value="placeholder")
        updates = []
        bot._update_message = lambda _message_id, text: updates.append(text)
        events = iter([("token", {"text": "不完整"})])
        with patch("src.feishu.bot.stream_knowledge_base", return_value=events):
            bot._stream_reply("source", "chat", "p2p", "问题", "existing-session")

        for _ in range(20):
            if updates:
                break
            time.sleep(0.02)
        assert updates == ["回答传输中断，请重新发送一次。"]


class TestFeishuWelcome:
    def test_p2p_entered_event_does_not_send_unsolicited_message(self):
        from types import SimpleNamespace
        from src.feishu.bot import FeishuBot

        bot = FeishuBot.__new__(FeishuBot)
        bot._reply = Mock()
        event = SimpleNamespace(event=SimpleNamespace(chat_id="chat_1"))

        bot._on_p2p_chat_entered(event)
        bot._on_p2p_chat_entered(event)

        bot._reply.assert_not_called()


class FakeClient:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json):
        self.url = url
        self.json = json
        return self.response


class TestAskKnowledgeBase:
    def test_posts_query_and_session(self):
        fake_response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"answer": "A", "conversation_id": "sid_9"},
        )
        fake_client = FakeClient(fake_response)
        with patch("src.feishu.bot.httpx.Client", return_value=fake_client):
            answer, session_id = ask_knowledge_base("q", "sid_1")
        assert (answer, session_id) == ("A", "sid_9")
        assert fake_client.json == {"query": "q", "session_id": "sid_1"}

    def test_posts_query_without_session(self):
        fake_response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"answer": "A", "conversation_id": None},
        )
        fake_client = FakeClient(fake_response)
        with patch("src.feishu.bot.httpx.Client", return_value=fake_client):
            ask_knowledge_base("q", None)
        assert fake_client.json == {"query": "q"}


class TestProcessMessage:
    def _run(self, text, store=None, session_id=None, ask=None):
        store = store or SessionStore(str(__import__("pathlib").Path(".") / "no_such.json"))
        replies = []
        if session_id:
            store.set("ou_1", session_id)

        def ask_fn(query, sid):
            if ask is not None:
                return ask(query, sid)
            return ("回答：" + query, "new_sid")

        process_incoming_message(
            store, lambda mid, cid, ct, t: replies.append(t),
            "msg_1", "chat_1", "p2p", text, "ou_1", ask_fn=ask_fn,
        )
        return store, replies

    def test_empty_text_gets_hint(self):
        _, replies = self._run("")
        assert replies == ["目前仅支持文本消息，请直接发送文字提问。"]

    def test_reset_word_clears_session(self):
        store, replies = self._run("/new", session_id="old_sid")
        assert store.get("ou_1") is None
        assert replies == ["已开启新会话，你可以开始提问了。"]

    def test_question_replies_and_saves_session(self):
        store, replies = self._run("什么是RAG？", session_id="old_sid")
        assert replies == ["回答：什么是RAG？"]
        assert store.get("ou_1") == "new_sid"

    def test_passes_existing_session_to_ask(self):
        seen = []

        def ask_fn(query, sid):
            seen.append(sid)
            return "A", "new_sid"

        self._run("q", session_id="old_sid", ask=ask_fn)
        assert seen == ["old_sid"]

    def test_kb_error_replies_friendly(self):
        def ask_fn(query, sid):
            raise RuntimeError("boom")

        _, replies = self._run("q", ask=ask_fn)
        assert replies == ["知识库暂时不可用，请稍后再试。"]

    def test_empty_answer_replies_no_content(self):
        def ask_fn(query, sid):
            return "", None

        _, replies = self._run("q", ask=ask_fn)
        assert replies == ["没有找到相关内容，换个问法试试？"]

    def test_session_commands_list_and_switch(self, tmp_path):
        store = SessionStore(tmp_path / "sessions.json")
        store.set("ou_1", "sid_1")
        store.set("ou_1", "sid_2")
        replies = []
        reply = lambda mid, cid, ctype, text: replies.append(text)
        process_incoming_message(store, reply, "m", "c", "p2p", "/sessions", "ou_1")
        process_incoming_message(store, reply, "m", "c", "p2p", "/use 2", "ou_1")
        assert "1. sid_2" in replies[0]
        assert "2. sid_1" in replies[0]
        assert store.get("ou_1") == "sid_1"

    def test_session_delete_removes_current_mapping(self, tmp_path):
        store = SessionStore(tmp_path / "sessions.json")
        store.set("ou_1", "sid_1")
        replies = []
        process_incoming_message(
            store,
            lambda mid, cid, ctype, text: replies.append(text),
            "m", "c", "p2p", "/delete 1", "ou_1",
        )
        assert store.get("ou_1") is None
        assert replies == ["已删除会话：sid_1"]

    def test_clear_all_removes_all_session_mappings(self, tmp_path):
        store = SessionStore(tmp_path / "sessions.json")
        store.set("ou_1", "sid_1")
        store.set("ou_1", "sid_2")
        replies = []
        with patch("src.agent.chat_history.delete_history", return_value=True) as delete:
            process_incoming_message(
                store,
                lambda mid, cid, ctype, text: replies.append(text),
                "m", "c", "p2p", "/clear-all", "ou_1",
            )
        assert store.list("ou_1") == []
        assert replies == [
            "已清空 2 个知识库历史会话。\n"
            "飞书聊天窗口中已经发送的提问和回答消息不会被删除；如需清空窗口，请在飞书客户端删除或新建会话。"
        ]
        assert delete.call_count == 2


class TestSessionStore:
    def test_set_get_clear(self, tmp_path):
        store = SessionStore(tmp_path / "sessions.json")
        assert store.get("ou_1") is None
        store.set("ou_1", "sid_1")
        assert store.get("ou_1") == "sid_1"
        assert store.clear("ou_1") is True
        assert store.get("ou_1") is None
        assert store.clear("ou_1") is False

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / "sessions.json"
        SessionStore(path).set("ou_1", "sid_1")
        assert SessionStore(path).get("ou_1") == "sid_1"

    def test_session_history_persists_and_switches(self, tmp_path):
        path = tmp_path / "sessions.json"
        store = SessionStore(path)
        store.set("ou_1", "sid_1")
        store.set("ou_1", "sid_2")
        restored = SessionStore(path)
        assert restored.list("ou_1") == ["sid_2", "sid_1"]
        assert restored.switch("ou_1", "sid_1") is True
        assert restored.get("ou_1") == "sid_1"
