from unittest.mock import MagicMock, patch

import pytest

import src.mcp_stdio as mcp_stdio


class TestMcpStdioTools:
    def test_tools_registered(self):
        tools = mcp_stdio.mcp._tool_manager.list_tools()
        names = sorted(t.name for t in tools)
        assert names == [
            "add_sync_dir",
            "answer_with_knowledge",
            "delete_session",
            "get_index_status",
            "get_sync_status",
            "list_files",
            "list_sessions",
            "remove_file",
            "remove_sync_dir",
            "run_sync",
            "search_knowledge",
            "set_graph_extraction_mode",
            "start_index_task",
            "system_status",
            "upload_documents",
        ]


class TestEnsureReady:
    def test_returns_manager_when_ready(self):
        rm = MagicMock()
        with (
            patch.object(mcp_stdio, "_ready") as ev,
            patch.object(mcp_stdio, "_start_error", None),
            patch.object(mcp_stdio, "ResourceManager") as RM,
        ):
            ev.wait.return_value = True
            RM.get_instance.return_value = rm
            assert mcp_stdio._ensure_ready() is rm

    def test_raises_on_start_error(self):
        with (
            patch.object(mcp_stdio, "_ready") as ev,
            patch.object(mcp_stdio, "_start_error", RuntimeError("boom")),
        ):
            ev.wait.return_value = True
            with pytest.raises(RuntimeError, match="boom"):
                mcp_stdio._ensure_ready()

    def test_raises_on_timeout(self):
        with patch.object(mcp_stdio, "_ready") as ev:
            ev.wait.return_value = False
            with pytest.raises(RuntimeError, match="超时"):
                mcp_stdio._ensure_ready(timeout=0.001)


class TestWarmup:
    def test_warmup_starts_and_signals(self):
        rm = MagicMock()
        with (
            patch.object(mcp_stdio, "ResourceManager") as RM,
            patch.object(mcp_stdio, "_ready") as ev,
        ):
            RM.get_instance.return_value = rm
            mcp_stdio._warmup()
            rm.startup.assert_called_once()
            ev.set.assert_called_once()

    def test_warmup_records_error(self):
        mcp_stdio._start_error = None
        with patch.object(mcp_stdio, "ResourceManager") as RM:
            RM.get_instance.side_effect = RuntimeError("init fail")
            mcp_stdio._warmup()
            assert isinstance(mcp_stdio._start_error, RuntimeError)
            mcp_stdio._start_error = None
