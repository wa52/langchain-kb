import json
import os
import re
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest
from typer.testing import CliRunner

from src.cli.knowledge import app

runner = CliRunner()
SNAP_DIR = Path(__file__).parent / "snapshots"
_ANSI = re.compile(r"\x1b\[")


def _doc(content, source="docs/rag.md", chunk_id="abc123", section="基础"):
    d = MagicMock()
    d.page_content = content
    d.metadata = {"source": source, "chunk_id": chunk_id, "section": section}
    d.id = chunk_id
    return d


def assert_snapshot(name: str, content: str):
    path = SNAP_DIR / f"{name}.snap"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")
        pytest.skip(f"snapshot written: {name}")
    assert path.read_text(encoding="utf-8") == content


class TestHelp:

    def test_help_shows_all_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ["serve", "index", "search", "chat", "status", "doctor"]:
            assert cmd in result.output

    def test_serve_help(self):
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output

    def test_index_help(self):
        result = runner.invoke(app, ["index", "--help"])
        assert result.exit_code == 0
        assert "--incremental" in result.output
        assert "--force" in result.output

    def test_search_help(self):
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "--top-k" in result.output
        assert "--plain" in result.output

    def test_doctor_help(self):
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.output


class TestServe:

    def test_serve_shows_addresses(self):
        with (
            patch("src.api.app.create_app"),
            patch("uvicorn.run"),
        ):
            result = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--port", "9000"])
        assert result.exit_code == 0
        assert "0.0.0.0:9000" in result.output
        assert "/docs" in result.output
        assert "/mcp" in result.output

    def test_serve_json(self):
        with (
            patch("src.api.app.create_app"),
            patch("uvicorn.run"),
        ):
            result = runner.invoke(app, ["serve", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert "mcp" in parsed["data"]

    def test_serve_failure_shows_reason(self):
        with (
            patch("src.api.app.create_app"),
            patch("uvicorn.run", side_effect=OSError("address in use")),
        ):
            result = runner.invoke(app, ["serve"])
        assert result.exit_code == 75
        assert "address in use" in result.output


class TestIndex:

    def test_index_dir_uses_run_add_path(self):
        with (
            patch("src.ingestion.pipeline.run_add_path", return_value=7) as mock_add,
            patch("src.ingestion.pipeline.run_single_file_update") as mock_single,
        ):
            result = runner.invoke(app, ["index", "./docs"])
        assert result.exit_code == 0
        mock_add.assert_called_once()
        mock_single.assert_not_called()
        assert "处理 7 个" in result.output

    def test_index_file_uses_single_file_update(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("src.ingestion.pipeline.run_single_file_update", return_value=3) as mock_single,
            patch("src.ingestion.pipeline.run_add_path") as mock_add,
        ):
            result = runner.invoke(app, ["index", "docs/rag.md"])
        assert result.exit_code == 0
        mock_single.assert_called_once()
        mock_add.assert_not_called()

    def test_index_missing_path_exit_3(self):
        result = runner.invoke(app, ["index", "./does/not/exist.md"])
        assert result.exit_code == 3

    def test_index_incremental(self):
        with (
            patch("src.ingestion.tracker.get_changed_files",
                  return_value=(["a.md"], ["b.md", "c.md"])),
            patch("src.ingestion.pipeline.run_incremental_update", return_value=5) as mock_upd,
        ):
            result = runner.invoke(app, ["index", "./docs", "--incremental"])
        assert result.exit_code == 0
        mock_upd.assert_called_once()
        assert "处理 1 个" in result.output
        assert "跳过 2 个" in result.output

    def test_index_force_file_replaces_source(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("src.ingestion.pipeline.run_single_file_update", return_value=2) as mock_upd,
        ):
            result = runner.invoke(app, ["index", "docs/rag.md", "--force"])
        assert result.exit_code == 0
        mock_upd.assert_called_once()

    def test_index_json_no_extra_text(self):
        with patch("src.ingestion.pipeline.run_add_path", return_value=10):
            result = runner.invoke(app, ["index", "./docs", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert parsed["data"]["processed"] == 10
        assert parsed["data"]["failed"] == 0
        assert _ANSI.search(result.output) is None

    def test_index_failure_exit_1(self):
        with patch("src.ingestion.pipeline.run_add_path", side_effect=RuntimeError("boom")):
            result = runner.invoke(app, ["index", "./docs"])
        assert result.exit_code == 1
        assert "boom" in result.output


class TestSearch:

    def test_search_plain_output(self):
        with patch("src.vector_store.chroma_client.get_vector_store") as mock_vs:
            mock_vs.return_value.similarity_search_with_relevance_scores.return_value = [
                (_doc("RAG 原理说明"), 0.92),
            ]
            result = runner.invoke(app, ["search", "RAG", "--plain"])
        assert result.exit_code == 0
        assert "docs/rag.md" in result.output
        assert "0.92" in result.output
        assert _ANSI.search(result.output) is None

    def test_search_table_output(self):
        with patch("src.vector_store.chroma_client.get_vector_store") as mock_vs:
            mock_vs.return_value.similarity_search_with_relevance_scores.return_value = [
                (_doc("RAG 原理说明"), 0.92),
            ]
            result = runner.invoke(app, ["search", "RAG"])
        assert result.exit_code == 0
        assert "docs/rag.md" in result.output
        assert "RAG 原理说明" in result.output

    def test_search_json(self):
        with patch("src.vector_store.chroma_client.get_vector_store") as mock_vs:
            mock_vs.return_value.similarity_search_with_relevance_scores.return_value = [
                (_doc("RAG 原理说明"), 0.92),
            ]
            result = runner.invoke(app, ["search", "RAG", "--json"])
        assert result.exit_code == 0
        assert_snapshot("search_json", result.output)
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert parsed["data"][0]["source"] == "docs/rag.md"
        assert parsed["data"][0]["score"] == 0.92
        assert _ANSI.search(result.output) is None

    def test_search_empty_returns_ok(self):
        with patch("src.vector_store.chroma_client.get_vector_store") as mock_vs:
            mock_vs.return_value.similarity_search_with_relevance_scores.return_value = []
            result = runner.invoke(app, ["search", "nothing"])
        assert result.exit_code == 0

    def test_search_top_k_passed(self):
        with patch("src.vector_store.chroma_client.get_vector_store") as mock_vs:
            mock_vs.return_value.similarity_search_with_relevance_scores.return_value = []
            runner.invoke(app, ["search", "q", "--top-k", "3"])
        mock_vs.return_value.similarity_search_with_relevance_scores.assert_called_once_with(
            "q", k=3
        )


class TestChat:

    def test_chat_shows_answer_and_sources(self):
        with patch("src.api.services.chat.chat_with_rag",
                   return_value=("答案是 X [来源: docs/rag.md]", "session_1", 123.4)):
            result = runner.invoke(app, ["chat", "什么是RAG?"])
        assert result.exit_code == 0
        assert "答案是 X" in result.output
        assert "docs/rag.md" in result.output

    def test_chat_json(self):
        with patch("src.api.services.chat.chat_with_rag",
                   return_value=("答案是 X [来源: docs/rag.md]", "session_1", 123.4)):
            result = runner.invoke(app, ["chat", "什么是RAG?", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert parsed["data"]["answer"] == "答案是 X"
        assert parsed["data"]["sources"] == ["docs/rag.md"]
        assert parsed["data"]["session_id"] == "session_1"
        assert _ANSI.search(result.output) is None

    def test_chat_session_passed(self):
        with patch("src.api.services.chat.chat_with_rag",
                   return_value=("ans", "session_1", 1.0)) as mock_chat:
            runner.invoke(app, ["chat", "q", "--session", "session_1"])
        mock_chat.assert_called_once_with("q", "session_1")

    def test_chat_failure_exit_1(self):
        with patch("src.api.services.chat.chat_with_rag", side_effect=RuntimeError("api down")):
            result = runner.invoke(app, ["chat", "q"])
        assert result.exit_code == 1
        assert "api down" in result.output


class TestStatus:

    def test_status_table(self):
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
        ):
            mock_vs.return_value.get_stats.return_value = {"count": 10, "sources": ["a"], "source_count": 1}
            mock_bm25.exists.return_value = True
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "向量库" in result.output
        assert "10" in result.output

    def test_status_json(self):
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
            patch("config.EMBEDDING_MODEL", "bge-small-zh"),
            patch("config.LLM_MODEL", "deepseek-chat"),
            patch("config.KNOWLEDGE_HOME", "C:/knowledge-home"),
            patch("config.DATA_DIR", Path("C:/knowledge-home/data/docs")),
            patch("config.GRAPH_PERSIST_DIR", Path("C:/knowledge-home/data")),
        ):
            mock_vs.return_value.get_stats.return_value = {"count": 10, "sources": ["a"], "source_count": 1}
            mock_bm25.exists.return_value = True
            result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        assert_snapshot("status_json", result.output)
        parsed = json.loads(result.output)
        assert parsed["data"]["vector_store"]["chunks"] == 10
        assert parsed["data"]["overall"] == "ok"
        assert parsed["data"]["components"]["graph"]["state"] == "pending"
        assert _ANSI.search(result.output) is None


class TestDoctor:

    def test_doctor_all_pass(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("config.DEEPSEEK_API_KEY", "sk-test"),
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.cli.knowledge._port_open", return_value=True),
        ):
            mock_vs.return_value.get_stats.return_value = {"count": 5, "sources": [], "source_count": 1}
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "✔" in result.output or "OK" in result.output

    def test_doctor_missing_api_key_exit_78(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("config.DEEPSEEK_API_KEY", ""),
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.cli.knowledge._port_open", return_value=True),
        ):
            mock_vs.return_value.get_stats.return_value = {"count": 5, "sources": [], "source_count": 1}
            result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 78
        assert "DEEPSEEK_API_KEY" in result.output or "API Key" in result.output

    def test_doctor_json(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("config.DEEPSEEK_API_KEY", "sk-test"),
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.cli.knowledge._port_open", return_value=True),
        ):
            mock_vs.return_value.get_stats.return_value = {"count": 5, "sources": [], "source_count": 1}
            result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        assert "checks" in parsed["data"]
        assert _ANSI.search(result.output) is None


class TestOutputDiscipline:

    def test_no_ansi_when_not_tty(self):
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
        ):
            mock_vs.return_value.get_stats.return_value = {"count": 10, "sources": [], "source_count": 1}
            mock_bm25.exists.return_value = True
            result = runner.invoke(app, ["status"])
        assert _ANSI.search(result.output) is None

    def test_no_color_env(self):
        import os
        with (
            patch.dict(os.environ, {"NO_COLOR": "1"}),
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
        ):
            mock_vs.return_value.get_stats.return_value = {"count": 10, "sources": [], "source_count": 1}
            mock_bm25.exists.return_value = True
            result = runner.invoke(app, ["status"])
        assert _ANSI.search(result.output) is None

    def test_unknown_command_exit_2(self):
        result = runner.invoke(app, ["nonexistent"])
        assert result.exit_code == 2

    def test_missing_argument_exit_2(self):
        result = runner.invoke(app, ["search"])
        assert result.exit_code == 2


class TestJsonErrorContract:

    def _assert_error(self, result, type_, exit_code, recoverable, stdout_empty=True):
        assert result.exit_code == exit_code
        if stdout_empty:
            assert result.stdout == ""
        parsed = json.loads(result.stderr)
        assert parsed["status"] == "error"
        err = parsed["error"]
        assert err["type"] == type_
        assert isinstance(err["message"], str) and err["message"]
        assert err["recoverable"] is recoverable
        assert isinstance(err["suggestions"], list)
        assert all(isinstance(s, str) and s for s in err["suggestions"])
        assert _ANSI.search(result.stderr) is None

    def test_index_json_missing_path(self):
        self._assert_error(
            runner.invoke(app, ["index", "./does/not/exist.md", "--json"]),
            type_="path_not_found", exit_code=3, recoverable=False)

    def test_index_json_pipeline_failure(self):
        with patch("src.ingestion.pipeline.run_add_path",
                   side_effect=RuntimeError("boom")):
            self._assert_error(
                runner.invoke(app, ["index", "./docs", "--json"]),
                type_="index_failed", exit_code=1, recoverable=True)

    def test_serve_json_port_busy(self):
        with (
            patch("src.api.app.create_app"),
            patch("uvicorn.run", side_effect=OSError("address in use")),
        ):
            self._assert_error(
                runner.invoke(app, ["serve", "--json"]),
                type_="port_busy", exit_code=75, recoverable=True, stdout_empty=False)

    def test_search_json_failure(self):
        with patch("src.vector_store.chroma_client.get_vector_store",
                   side_effect=RuntimeError("vector store down")):
            self._assert_error(
                runner.invoke(app, ["search", "q", "--json"]),
                type_="search_failed", exit_code=1, recoverable=True)

    def test_chat_json_failure(self):
        with patch("src.api.services.chat.chat_with_rag",
                   side_effect=RuntimeError("api down")):
            self._assert_error(
                runner.invoke(app, ["chat", "q", "--json"]),
                type_="chat_failed", exit_code=1, recoverable=True)


class TestColorMode:

    def _invoke_status(self, monkeypatch, args=None, env=None):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
        ):
            mock_vs.return_value.get_stats.return_value = {
                "count": 10, "sources": [], "source_count": 1}
            mock_bm25.exists.return_value = True
            return runner.invoke(app, (args or []) + ["status"])

    def test_color_auto_off_when_not_tty(self, monkeypatch):
        result = self._invoke_status(monkeypatch)
        assert result.exit_code == 0
        assert _ANSI.search(result.output) is None

    def test_color_always_forces_ansi(self, monkeypatch):
        result = self._invoke_status(monkeypatch, ["--color", "always"])
        assert result.exit_code == 0
        assert _ANSI.search(result.output) is not None

    def test_color_never_disables(self, monkeypatch):
        result = self._invoke_status(monkeypatch, ["--color", "never"])
        assert result.exit_code == 0
        assert _ANSI.search(result.output) is None

    def test_no_color_alias_disables(self, monkeypatch):
        result = self._invoke_status(monkeypatch, ["--no-color"])
        assert result.exit_code == 0
        assert _ANSI.search(result.output) is None

    def test_color_always_beats_no_color_env(self, monkeypatch):
        result = self._invoke_status(
            monkeypatch, ["--color", "always"], env={"NO_COLOR": "1"})
        assert result.exit_code == 0
        assert _ANSI.search(result.output) is not None

    def test_term_dumb_disables_in_auto(self, monkeypatch):
        result = self._invoke_status(monkeypatch, env={"TERM": "dumb"})
        assert result.exit_code == 0
        assert _ANSI.search(result.output) is None

    def test_force_color_enables(self, monkeypatch):
        result = self._invoke_status(monkeypatch, env={"FORCE_COLOR": "1"})
        assert result.exit_code == 0
        assert _ANSI.search(result.output) is not None

    def test_force_color_wins_over_color_never(self, monkeypatch):
        result = self._invoke_status(
            monkeypatch, ["--color", "never"], env={"FORCE_COLOR": "1"})
        assert result.exit_code == 0
        assert _ANSI.search(result.output) is not None

    def test_invalid_color_value_is_usage_error(self):
        result = runner.invoke(app, ["--color", "bogus", "status"])
        assert result.exit_code == 2
        assert "--color" in result.output


class TestHelpDiscovery:

    def test_no_args_shows_concise_help(self):
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "示例" in result.output
        assert "--help" in result.output
        assert "index" in result.output
        assert "search" in result.output

    def test_short_help_flag(self):
        result = runner.invoke(app, ["-h"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_subcommand_short_help_flag(self):
        result = runner.invoke(app, ["search", "-h"])
        assert result.exit_code == 0
        assert "--top-k" in result.output

    def test_help_subcommand_lists_commands(self):
        result = runner.invoke(app, ["help"])
        assert result.exit_code == 0
        for cmd in ["serve", "index", "search", "chat", "status", "doctor"]:
            assert cmd in result.output

    def test_help_subcommand_topic(self):
        result = runner.invoke(app, ["help", "serve"])
        assert result.exit_code == 0
        assert "--port" in result.output

    def test_help_subcommand_unknown_exit_2(self):
        result = runner.invoke(app, ["help", "nope"])
        assert result.exit_code == 2

    def test_full_help_has_examples(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "示例" in result.output
        assert "index ./docs" in result.output


class TestWebCommand:

    def test_web_json_output(self):
        with (
            patch("src.api.app.create_app"),
            patch("uvicorn.run"),
        ):
            result = runner.invoke(app, ["web", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "ok"
        for key in ["url", "web", "swagger", "mcp"]:
            assert key in parsed["data"]

    def test_web_no_open_by_default(self):
        with (
            patch("src.api.app.create_app"),
            patch("uvicorn.run"),
            patch("webbrowser.open") as mock_open,
        ):
            result = runner.invoke(app, ["web"])
        assert result.exit_code == 0
        mock_open.assert_not_called()

    def test_web_open_calls_browser(self):
        with (
            patch("src.api.app.create_app"),
            patch("uvicorn.run"),
            patch("webbrowser.open") as mock_open,
        ):
            result = runner.invoke(app, ["web", "--open"])
        assert result.exit_code == 0
        mock_open.assert_called_once_with("http://127.0.0.1:8000/")

    def test_web_open_skipped_in_json(self):
        with (
            patch("src.api.app.create_app"),
            patch("uvicorn.run"),
            patch("webbrowser.open") as mock_open,
        ):
            result = runner.invoke(app, ["web", "--open", "--json"])
        assert result.exit_code == 0
        mock_open.assert_not_called()

    def test_web_port_busy_exit_75(self):
        with (
            patch("src.api.app.create_app"),
            patch("uvicorn.run", side_effect=OSError("address in use")),
        ):
            result = runner.invoke(app, ["web", "--json"])
        assert result.exit_code == 75


class TestCliCommand:

    def test_cli_runs_console(self):
        with patch("src.cli.console.run_console") as mock_console:
            result = runner.invoke(app, ["cli"])
        assert result.exit_code == 0
        mock_console.assert_called_once()


class TestKnowledgeHomeVisibility:

    def test_status_json_includes_knowledge_home(self):
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
            patch("config.KNOWLEDGE_HOME", "C:/knowledge-home"),
        ):
            mock_vs.return_value.get_stats.return_value = {
                "count": 10, "sources": ["a"], "source_count": 1}
            mock_bm25.exists.return_value = True
            result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["data"]["knowledge_home"] == "C:/knowledge-home"

    def test_status_table_shows_knowledge_home(self):
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
            patch("config.KNOWLEDGE_HOME", "C:/knowledge-home"),
        ):
            mock_vs.return_value.get_stats.return_value = {
                "count": 10, "sources": ["a"], "source_count": 1}
            mock_bm25.exists.return_value = True
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "C:/knowledge-home" in result.output

    def test_doctor_json_includes_knowledge_home_check(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("config.DEEPSEEK_API_KEY", "sk-test"),
            patch("config.KNOWLEDGE_HOME", "C:/knowledge-home"),
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.cli.knowledge._port_open", return_value=True),
        ):
            mock_vs.return_value.get_stats.return_value = {
                "count": 5, "sources": [], "source_count": 1}
            result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        names = [c["name"] for c in parsed["data"]["checks"]]
        assert "数据目录" in names

    def test_no_args_help_lists_web_and_cli(self):
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "knowledge web" in result.output
        assert "knowledge cli" in result.output

    def test_full_help_lists_web_and_cli(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "web" in result.output
        assert "cli" in result.output


class TestAutomaticSetup:

    def test_status_json_includes_data_dir(self):
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
            patch("config.KNOWLEDGE_HOME", "C:/knowledge-home"),
            patch("config.DATA_DIR", Path("C:/knowledge-home/data/docs")),
        ):
            mock_vs.return_value.get_stats.return_value = {
                "count": 10, "sources": ["a"], "source_count": 1}
            mock_bm25.exists.return_value = True
            result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["data"]["data_dir"] == str(Path("C:/knowledge-home/data/docs"))

    def test_status_table_shows_data_dir(self):
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
            patch("config.KNOWLEDGE_HOME", "C:/knowledge-home"),
            patch("config.DATA_DIR", Path("C:/knowledge-home/data/docs")),
        ):
            mock_vs.return_value.get_stats.return_value = {
                "count": 10, "sources": ["a"], "source_count": 1}
            mock_bm25.exists.return_value = True
            result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert str(Path("C:/knowledge-home/data/docs")) in result.output

    def test_doctor_json_includes_data_dir_check(self):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("config.DEEPSEEK_API_KEY", "sk-test"),
            patch("config.KNOWLEDGE_HOME", "C:/knowledge-home"),
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.cli.knowledge._port_open", return_value=True),
        ):
            mock_vs.return_value.get_stats.return_value = {
                "count": 5, "sources": [], "source_count": 1}
            result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0
        names = [c["name"] for c in json.loads(result.output)["data"]["checks"]]
        assert "源文档目录" in names

    def test_callback_ensures_data_dirs(self):
        with (
            patch("src.vector_store.service.VectorStoreService") as mock_vs,
            patch("src.vector_store.embedding.get_embedding_model"),
            patch("src.llm.get_llm"),
            patch("src.cli.knowledge._port_open", return_value=False),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH") as mock_bm25,
            patch("config.ensure_data_dirs") as mock_ensure,
        ):
            mock_vs.return_value.get_stats.return_value = {
                "count": 0, "sources": [], "source_count": 0}
            mock_bm25.exists.return_value = False
            result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0
        mock_ensure.assert_called()
