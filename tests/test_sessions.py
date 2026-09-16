import json
import threading
import time
from unittest.mock import patch, MagicMock

import pytest

import src.cli.console as console_mod
from src.agent.chat_history import _session_title, _MAX_TITLE_LEN


@pytest.fixture
def state():
    return {"agent": None, "messages": [], "session_id": None}


class TestSessionTitle:

    def test_title_from_first_user_message(self):
        msgs = [
            {"role": "user", "content": "什么是LangChain RAG?"},
            {"role": "assistant", "content": "LangChain是一个..."},
        ]
        assert _session_title(msgs) == "什么是LangChain RAG?"

    def test_title_skips_system_messages(self):
        msgs = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "如何构建知识库?"},
        ]
        assert _session_title(msgs) == "如何构建知识库?"

    def test_title_truncated_when_long(self):
        content = "A" * (_MAX_TITLE_LEN + 10)
        msgs = [{"role": "user", "content": content}]
        result = _session_title(msgs)
        assert len(result) == _MAX_TITLE_LEN
        assert result.endswith("…")

    def test_title_multiline_first_line_only(self):
        msgs = [
            {"role": "user", "content": "第一行\n第二行\n第三行"},
        ]
        assert _session_title(msgs) == "第一行"

    def test_title_strips_whitespace(self):
        msgs = [
            {"role": "user", "content": "  Hello World!  "},
        ]
        assert _session_title(msgs) == "Hello World!"

    def test_title_empty_messages_returns_empty_session(self):
        assert _session_title([]) == "空会话"

    def test_title_no_user_message_returns_empty_session(self):
        msgs = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "assistant", "content": "你好!"},
        ]
        assert _session_title(msgs) == "空会话"

    def test_title_empty_user_content_returns_empty_session(self):
        msgs = [{"role": "user", "content": ""}]
        assert _session_title(msgs) == "空会话"

    def test_title_whitespace_only_user_content_returns_empty_session(self):
        msgs = [{"role": "user", "content": "   \n  "}]
        assert _session_title(msgs) == "空会话"

    def test_title_user_content_is_none(self):
        msgs = [{"role": "user", "content": None}]
        assert _session_title(msgs) == "空会话"


class TestListSessionsEnhanced:

    def test_returns_title_and_turns(self, tmp_path):
        import src.agent.chat_history as ch
        session_dir = tmp_path / "chat_history"
        session_dir.mkdir()
        messages = [
            {"role": "user", "content": "什么是LangChain?"},
            {"role": "assistant", "content": "LangChain是一个框架"},
        ]
        f = session_dir / "session_test123.json"
        f.write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")

        with patch.object(ch, "HISTORY_DIR", session_dir):
            sessions = ch.list_sessions()

        assert len(sessions) == 1
        s = sessions[0]
        assert s["id"] == "session_test123"
        assert s["title"] == "什么是LangChain?"
        assert s["turns"] == 1

    def test_multi_turn_session(self, tmp_path):
        import src.agent.chat_history as ch
        session_dir = tmp_path / "chat_history"
        session_dir.mkdir()
        messages = [
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "答1"},
            {"role": "user", "content": "第二问"},
            {"role": "assistant", "content": "答2"},
            {"role": "user", "content": "第三问"},
            {"role": "assistant", "content": "答3"},
        ]
        f = session_dir / "session_multi.json"
        f.write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")

        with patch.object(ch, "HISTORY_DIR", session_dir):
            sessions = ch.list_sessions()

        assert len(sessions) == 1
        assert sessions[0]["turns"] == 3

    def test_empty_session_file_handled(self, tmp_path):
        import src.agent.chat_history as ch
        session_dir = tmp_path / "chat_history"
        session_dir.mkdir()
        f = session_dir / "session_empty.json"
        f.write_text("[]", encoding="utf-8")

        with patch.object(ch, "HISTORY_DIR", session_dir):
            sessions = ch.list_sessions()

        assert len(sessions) == 1
        assert sessions[0]["title"] == "空会话"
        assert sessions[0]["turns"] == 0

    def test_keeps_created_field(self, tmp_path):
        import src.agent.chat_history as ch
        import time
        session_dir = tmp_path / "chat_history"
        session_dir.mkdir()
        f = session_dir / "session_t.json"
        f.write_text("[]", encoding="utf-8")

        with patch.object(ch, "HISTORY_DIR", session_dir):
            sessions = ch.list_sessions()

        assert "created" in sessions[0]


class TestAllocateSessionId:

    def _patch_now(self, fixed):
        import src.agent.chat_history as ch
        import datetime as dt
        fake = type("FixedDatetime", (), {"now": staticmethod(lambda: fixed)})
        return patch.object(ch, "datetime", fake)

    def test_preallocates_underscore_microsecond_id(self, tmp_path):
        import src.agent.chat_history as ch
        import datetime as dt
        session_dir = tmp_path / "chat_history"
        session_dir.mkdir()
        fixed = dt.datetime(2026, 8, 15, 10, 30, 45, 123456)
        with patch.object(ch, "HISTORY_DIR", session_dir), self._patch_now(fixed):
            sid = ch.allocate_session_id()
        assert sid == "session_20260815_103045_123456"

    def test_appends_suffix_when_base_exists(self, tmp_path):
        import src.agent.chat_history as ch
        import datetime as dt
        session_dir = tmp_path / "chat_history"
        session_dir.mkdir()
        fixed = dt.datetime(2026, 8, 15, 10, 30, 45, 123456)
        base = "session_20260815_103045_123456"
        (session_dir / f"{base}.json").write_text("[]", encoding="utf-8")
        with patch.object(ch, "HISTORY_DIR", session_dir), self._patch_now(fixed):
            sid = ch.allocate_session_id()
        assert sid == f"{base}_1"

    def test_consecutive_calls_differ(self, tmp_path):
        import src.agent.chat_history as ch
        session_dir = tmp_path / "chat_history"
        session_dir.mkdir()
        with patch.object(ch, "HISTORY_DIR", session_dir):
            a = ch.allocate_session_id()
            b = ch.allocate_session_id()
        assert a != b


class TestSessionPersistenceSafety:

    def test_rejects_path_traversal_session_id(self, tmp_path):
        import src.agent.chat_history as ch
        with patch.object(ch, "HISTORY_DIR", tmp_path):
            with pytest.raises(ValueError, match="非法会话 ID"):
                ch.save_history([], "../outside")
            with pytest.raises(ValueError, match="非法会话 ID"):
                ch.load_history(r"..\outside")

    def test_save_is_atomic_and_leaves_no_temp_file(self, tmp_path):
        import src.agent.chat_history as ch
        messages = [{"role": "user", "content": "hello"}]
        with patch.object(ch, "HISTORY_DIR", tmp_path):
            session_id = ch.save_history(messages, "session_safe")
        assert session_id == "session_safe"
        assert json.loads((tmp_path / "session_safe.json").read_text(encoding="utf-8")) == messages
        assert list(tmp_path.glob("*.tmp")) == []

    def test_delete_waits_for_active_session_transaction(self, tmp_path):
        import src.agent.chat_history as ch

        entered = threading.Event()
        release = threading.Event()

        def active_writer():
            with ch.session_lock("session_busy"):
                entered.set()
                release.wait(timeout=2)
                ch.save_history([{"role": "user", "content": "done"}], "session_busy")

        with patch.object(ch, "HISTORY_DIR", tmp_path):
            writer = threading.Thread(target=active_writer)
            writer.start()
            assert entered.wait(timeout=1)
            deleted = []
            deleter = threading.Thread(
                target=lambda: deleted.append(ch.delete_history("session_busy"))
            )
            deleter.start()
            time.sleep(0.05)
            assert deleter.is_alive()
            release.set()
            writer.join(timeout=2)
            deleter.join(timeout=2)

        assert deleted == [True]
        assert not (tmp_path / "session_busy.json").exists()

    def test_session_lock_creates_reusable_file_lock(self, tmp_path):
        import src.agent.chat_history as ch

        with patch.object(ch, "HISTORY_DIR", tmp_path):
            with ch.session_lock("session_filelock"):
                lock_file = tmp_path / ".session_filelock.lock"
                assert lock_file.exists()
                entry = ch._SESSION_FILE_LOCKS["session_filelock"]
                assert entry[1] == 1
                # nested acquisition keeps a single OS lock with refcount 2
                with ch.session_lock("session_filelock"):
                    assert ch._SESSION_FILE_LOCKS["session_filelock"][1] == 2
                assert ch._SESSION_FILE_LOCKS["session_filelock"][1] == 1
            assert "session_filelock" not in ch._SESSION_FILE_LOCKS


class TestTrackerSnapshotRestore:

    def test_restore_reverts_tracker_changes(self, tmp_path):
        import src.ingestion.tracker as tr

        orig = tr.TRACKER_FILE
        tr.TRACKER_FILE = str(tmp_path / "file_tracker.json")
        try:
            tr.update_tracker("external", tmp_path, [])
            snapshot = tr.snapshot_tracker()
            (tmp_path / "new.md").write_text("内容", encoding="utf-8")
            tr.update_tracker("external", tmp_path, [str(tmp_path / "new.md")])
            registry = tr._load_tracker()["external"]
            assert "new.md" in registry
            tr.restore_tracker(snapshot)
            registry = tr._load_tracker()["external"]
            assert "new.md" not in registry
        finally:
            tr.TRACKER_FILE = orig


class TestSessionsCommandDisplay:

    def test_slash_sessions_shows_title_header(self, state):
        from src.cli.console import handle_command
        with (
            patch("src.cli.console.list_sessions") as mock_list,
            patch.object(console_mod, "_agent_ready") as mock_ready,
            patch.object(console_mod, "_agent_result", (MagicMock(), MagicMock())),
        ):
            mock_ready.is_set.return_value = True
            mock_list.return_value = [
                {"id": "session_123", "created": "2026-07-30 10:13",
                 "title": "什么是RAG?", "turns": 3},
            ]
            result = handle_command("/sessions", state)
            assert "标题" in result

    def test_slash_sessions_shows_title_content(self, state):
        from src.cli.console import handle_command
        with (
            patch("src.cli.console.list_sessions") as mock_list,
            patch.object(console_mod, "_agent_ready") as mock_ready,
            patch.object(console_mod, "_agent_result", (MagicMock(), MagicMock())),
        ):
            mock_ready.is_set.return_value = True
            mock_list.return_value = [
                {"id": "session_123", "created": "2026-07-30 10:13",
                 "title": "什么是RAG?", "turns": 3},
            ]
            result = handle_command("/sessions", state)
            assert "什么是RAG?" in result
