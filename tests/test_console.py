import sys
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

import src.cli.console as console_mod
from src.cli.console import handle_command


@pytest.fixture
def state():
    return {"agent": None, "messages": [], "session_id": None}


class TestHandleCommand:

    @pytest.fixture(autouse=True)
    def _ready_agent(self):
        with (
            patch.object(console_mod, "_agent_ready") as mock_ev,
            patch.object(console_mod, "_agent_result", (MagicMock(), MagicMock())),
        ):
            mock_ev.is_set.return_value = True
            yield

    def test_plain_text_returns_empty(self, state):
        result = handle_command("什么是 RAG", state)
        assert result == ""

    def test_empty_line(self, state):
        result = handle_command("", state)
        assert result == ""

    def test_help(self, state):
        result = handle_command("/help", state)
        assert "可用命令" in result
        assert "/add" in result
        assert "/exit" in result

    def test_exit(self, state):
        result = handle_command("/exit", state)
        assert result is None

    def test_new(self, state):
        state["messages"] = [{"role": "user", "content": "hello"}]
        state["session_id"] = "old_session"
        result = handle_command("/new", state)
        assert state["messages"] == []
        assert state["session_id"] is None

    def test_add(self, state):
        with patch("src.cli.console.run_add_path", return_value=3) as mock_add:
            result = handle_command("/add test.md", state)
            mock_add.assert_called_once()
            assert "成功添加" in result

    def test_add_no_arg(self, state):
        result = handle_command("/add", state)
        assert "用法" in result

    def test_remove(self, state):
        with patch("src.cli.console.run_remove") as mock_remove:
            result = handle_command("/remove test.md", state)
            mock_remove.assert_called_once()
            assert "已处理" in result

    def test_resume_not_found(self, state):
        with patch("src.cli.console.load_history", return_value=None):
            result = handle_command("/resume unknown_id", state)
            assert "未找到" in result

    def test_resume_restored(self, state):
        fake_msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        with patch("src.cli.console.load_history", return_value=fake_msgs):
            result = handle_command("/resume session_123", state)
            assert state["messages"] == fake_msgs
            assert state["session_id"] == "session_123"
            assert "恢复" in result

    def test_mode_show(self, state):
        with patch("config.ENABLE_GRAPH_LLM_EXTRACTION", True):
            result = handle_command("/mode", state)
            assert "LLM" in result

    def test_mode_switch(self, state):
        with (
            patch("src.cli.console.ENABLE_GRAPH_LLM_EXTRACTION", True),
            patch("dotenv.find_dotenv", return_value=".env"),
            patch("dotenv.set_key"),
        ):
            result = handle_command("/mode jieba", state)
            assert "JIEBA" in result

    def test_unknown_command(self, state):
        result = handle_command("/xyz", state)
        assert "未知命令" in result

    def test_config(self, state):
        result = handle_command("/config", state)
        assert "当前配置" in result
        assert "知识图谱" in result

    def test_stats(self, state):
        with (
            patch("src.vector_store.chroma_client.get_collection_stats") as mock_stats,
            patch("src.ingestion.tracker.list_all_files", return_value=[]),
        ):
            mock_stats.return_value = {"count": 1000, "source_count": 50, "sources": []}
            result = handle_command("/stats", state)
            assert "1000" in result
            assert "50" in result


class TestLoadingState:

    def test_command_blocked_during_loading(self, state):
        with patch.object(console_mod, "_agent_ready") as mock_ready:
            mock_ready.is_set.return_value = False
            result = handle_command("/stats", state)
            assert "正在加载" in result

    def test_plain_text_blocked_during_loading(self, state):
        with patch.object(console_mod, "_agent_ready") as mock_ready:
            mock_ready.is_set.return_value = False
            result = handle_command("你好", state)
            assert "正在加载" in result

    def test_help_works_during_loading(self, state):
        with patch.object(console_mod, "_agent_ready") as mock_ready:
            mock_ready.is_set.return_value = False
            result = handle_command("/help", state)
            assert "可用命令" in result

    def test_sessions_works_during_loading(self, state):
        with patch.object(console_mod, "_agent_ready") as mock_ready:
            mock_ready.is_set.return_value = False
            with patch("src.cli.console.list_sessions", return_value=[]):
                result = handle_command("/sessions", state)
                assert "暂无历史会话" in result

    def test_plain_text_works_after_ready(self, state):
        with (
            patch.object(console_mod, "_agent_ready") as mock_ready,
            patch.object(console_mod, "_agent_result", (MagicMock(), MagicMock())),
        ):
            mock_ready.is_set.return_value = True
            result = handle_command("你好", state)
            assert result == ""

    def test_command_works_after_ready(self, state):
        with (
            patch.object(console_mod, "_agent_ready") as mock_ready,
            patch.object(console_mod, "_agent_result", (MagicMock(), MagicMock())),
        ):
            mock_ready.is_set.return_value = True
            with (
                patch("src.cli.console.run_add_path", return_value=3),
            ):
                result = handle_command("/add test.md", state)
                assert "成功添加" in result

    def test_plain_text_blocked_after_failure(self, state):
        with patch.object(console_mod, "_agent_ready") as mock_ready:
            mock_ready.is_set.return_value = True
            with patch.object(console_mod, "_agent_result", Exception("no api key")):
                result = handle_command("你好", state)
                assert "加载失败" in result

    def test_help_works_after_failure(self, state):
        with patch.object(console_mod, "_agent_ready") as mock_ready:
            mock_ready.is_set.return_value = True
            with patch.object(console_mod, "_agent_result", Exception("no api key")):
                result = handle_command("/help", state)
                assert "可用命令" in result


class TestEchoCarriageReturn:

    def test_echo_with_cr_bypasses_pt_print(self):
        buf = StringIO()
        with patch.object(console_mod, "_HAS_PROMPT_TOOLKIT", True):
            with patch("sys.stdout", buf):
                with patch("prompt_toolkit.print_formatted_text") as mock_pt:
                    console_mod.echo("\r[ 50%] ##########..........  75/500", end="")
                    mock_pt.assert_not_called()
                    assert "\r" in buf.getvalue()

    def test_echo_without_cr_uses_pt_print(self):
        buf = StringIO()
        with patch.object(console_mod, "_HAS_PROMPT_TOOLKIT", True):
            with patch("sys.stdout", buf):
                with patch("prompt_toolkit.print_formatted_text") as mock_pt:
                    console_mod.echo("hello world")
                    mock_pt.assert_called_once()

    def test_echo_cr_fallback_no_pt(self):
        buf = StringIO()
        with patch.object(console_mod, "_HAS_PROMPT_TOOLKIT", False):
            with patch("sys.stdout", buf):
                with patch.object(console_mod, "_cli_echo") as mock_cli:
                    console_mod.echo("\rprogress")
                    mock_cli.assert_called_once()
                    args = mock_cli.call_args[0]
                    assert "\r" in args[0]
