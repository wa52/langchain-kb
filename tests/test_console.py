from unittest.mock import patch, MagicMock

import pytest

from src.cli.console import handle_command


@pytest.fixture
def state():
    return {"agent": None, "messages": [], "session_id": None}


class TestHandleCommand:

    def test_plain_text_returns_none(self, state):
        result = handle_command("什么是 RAG", state)
        assert result is None

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
