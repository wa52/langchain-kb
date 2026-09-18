import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.feishu.bot import (
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
